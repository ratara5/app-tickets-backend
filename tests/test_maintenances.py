import json
import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.master import Market, Equipment, Technician
from app.models.ticket import Ticket
from app.models.maintenance import Maintenance
from app.models.worksheet import Worksheet
from app.models.fsm_user import FSMUser
from app.core.security import hash_password


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket for maintenance",
    "priority": "NORMAL",
    "status": "OPEN",
    "market_id": 1,
    "equipment_id": 1,
}


def _create_assigned_started_ticket(
    client: TestClient, auth_headers: dict
) -> int:
    resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    return ticket_id


def test_create_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ticket_id"] == ticket_id


def test_create_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.post(
        "/maintenances",
        json={
            "maintenance_id": "00000000-0000-0000-0000-000000000001",
            "ticket_id": 1,
            "maintenance_date": datetime.now().isoformat(),
        }
    )
    assert response.status_code == 401


def test_create_maintenance_invalid_data(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post("/maintenances", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_list_maintenances(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/maintenances", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_maintenances_unauthorized(
    client: TestClient
) -> None:
    response = client.get("/maintenances")
    assert response.status_code == 401


def test_get_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000002"
    create_resp = client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    mid = create_resp.json()["maintenance_id"]
    response = client.get(f"/maintenances/{mid}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["maintenance_id"] == mid


def test_get_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get(
        "/maintenances/00000000-0000-0000-0000-000000000099",
        headers=auth_headers
    )
    assert response.status_code == 404


def test_get_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.get("/maintenances/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 401


def test_update_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000001",
        data={"payload": '{"maintenance_description": "Updated"}'}
    )
    assert response.status_code == 401


def test_update_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000099",
        data={"payload": '{"maintenance_description": "Updated"}'},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_update_maintenance_reconciles_pauses_no_duplicates(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """PATCH /maintenances/{id} must REPLACE the child collections, not append.

    Regression: the mobile form re-sends its full current pause list on every
    save. The previous append-only behavior re-inserted already-persisted
    pauses on every save, duplicating rows across a pause -> continue -> save
    cycle. This asserts re-saving the identical payload does not grow the
    persisted pause list.
    """
    resp = client.post(
        "/tickets",
        json={**TICKET_PAYLOAD, "ticket_date": "2026-08-31"},
        headers=auth_headers,
    )
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    start_resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    mid = start_resp.json()["maintenance_id"]

    payload = {
        "maintenance_description": "Updated",
        "pauses": [
            {"pause_reason": "PAU 1", "created_at": "2030-01-01T03:00:05.579Z"}
        ],
    }

    first = client.patch(
        f"/maintenances/{mid}",
        data={"payload": json.dumps(payload)},
        headers=auth_headers
    )
    assert first.status_code == 200
    assert [p["pause_reason"] for p in first.json()["pauses"]] == ["PAU 1"]

    # pause -> continue : a future-dated pause marks the ticket PAUSED, and
    # Continue reopens it to IN_PROGRESS so it can be saved again.
    continue_resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert continue_resp.status_code in (200, 201)

    # Second save (pause -> continue -> save) with identical state: nothing
    # new was edited, so nothing may be re-appended.
    second = client.patch(
        f"/maintenances/{mid}",
        data={"payload": json.dumps(payload)},
        headers=auth_headers
    )
    assert second.status_code == 200
    assert [p["pause_reason"] for p in second.json()["pauses"]] == ["PAU 1"]

    # Persisted state must stay a single row after a fresh read.
    fetched = client.get(f"/maintenances/{mid}", headers=auth_headers)
    assert fetched.status_code == 200
    assert [p["pause_reason"] for p in fetched.json()["pauses"]] == ["PAU 1"]
    assert len(fetched.json()["pauses"]) == 1


def test_pause_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000003"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    response = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Test pause"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PAUSED"


def test_pause_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000001/pause",
        json={"pause_reason": "Test"}
    )
    assert response.status_code == 401


def test_pause_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000099/pause",
        json={"pause_reason": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_delete_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000004"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    response = client.delete(
        f"/maintenances/{maintenance_id}",
        headers=auth_headers
    )
    assert response.status_code == 204


def test_delete_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.delete(
        "/maintenances/00000000-0000-0000-0000-000000000001"
    )
    assert response.status_code == 401


def test_update_maintenance_initial_photo_action_keep(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """PATCH with initial_photo_action=keep preserves the existing photo."""
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000010"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers,
    )
    response = client.patch(
        f"/maintenances/{maintenance_id}",
        data={
            "payload": json.dumps({"maintenance_description": "Updated"}),
            "initial_photo_action": "keep",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_update_maintenance_initial_photo_action_invalid_action(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """PATCH with invalid initial_photo_action returns 422."""
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000011"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers,
    )
    response = client.patch(
        f"/maintenances/{maintenance_id}",
        data={
            "payload": json.dumps({"maintenance_description": "Updated"}),
            "initial_photo_action": "invalid_action",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_update_maintenance_initial_photo_action_replace_without_file(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """PATCH with initial_photo_action=replace but no file returns 422."""
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000012"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers,
    )
    response = client.patch(
        f"/maintenances/{maintenance_id}",
        data={
            "payload": json.dumps({"maintenance_description": "Updated"}),
            "initial_photo_action": "replace",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_delete_maintenance_photo_not_found(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """DELETE a photo that doesn't exist returns 404."""
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000013"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers,
    )
    response = client.delete(
        f"/maintenances/{maintenance_id}/photos/99999",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_delete_maintenance_photo_unauthorized(
    client: TestClient
) -> None:
    """DELETE photo without auth returns 401."""
    response = client.delete(
        "/maintenances/00000000-0000-0000-0000-000000000001/photos/1"
    )
    assert response.status_code == 401


# ── Sign action (change: add-signed-ticket-status) ────────────────────────────

_WEEKDAY = "2026-08-31"  # Monday, non-holiday -> normal working day


def _create_weekday_started_maintenance(
    client: TestClient, auth_headers: dict
) -> str:
    """Create + assign + start a ticket on a weekday. Returns maintenance_id."""
    resp = client.post(
        "/tickets",
        json={**TICKET_PAYLOAD, "ticket_date": _WEEKDAY},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    start_resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert start_resp.status_code == 201, start_resp.text
    return start_resp.json()["maintenance_id"]


def _save_and_close_ticket(
    client: TestClient, auth_headers: dict, mid: str
) -> None:
    """PATCH the maintenance, which moves the owner ticket to CLOSED (weekday)."""
    resp = client.patch(
        f"/maintenances/{mid}",
        data={"payload": json.dumps({"maintenance_description": "Closed maintenance"})},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


def _mark_worksheet_pdf_generated(
    client: TestClient, auth_headers: dict, db_session: Session, mid: str
) -> None:
    """Create the (draft) worksheet and force a generated PDF state in DB."""
    resp = client.get(f"/maintenances/{mid}/worksheet", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ws = db_session.query(Worksheet).filter(
        Worksheet.maintenance_id == uuid.UUID(mid)
    ).first()
    assert ws is not None
    ws.closed = True
    ws.pdf_path = "tests/signed.pdf"
    ws.sheet_number = "WS-2026-000001"
    db_session.commit()


def test_sign_maintenance_success(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_weekday_started_maintenance(client, auth_headers)
    _save_and_close_ticket(client, auth_headers, mid)
    _mark_worksheet_pdf_generated(client, auth_headers, db_session, mid)
    ticket = db_session.query(Ticket).join(Maintenance).filter(
        Maintenance.maintenance_id == uuid.UUID(mid)
    ).first()
    assert ticket.status == "CLOSED"

    response = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["ticket_id"] == ticket.ticket_id

    db_session.expire_all()
    ticket = db_session.query(Ticket).join(Maintenance).filter(
        Maintenance.maintenance_id == uuid.UUID(mid)
    ).first()
    assert ticket.status == "SIGNED"


def test_sign_maintenance_ticket_not_closed(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_weekday_started_maintenance(client, auth_headers)
    response = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert response.status_code == 422
    assert "Invalid transition" in response.text


def test_sign_maintenance_missing_pdf(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_weekday_started_maintenance(client, auth_headers)
    _save_and_close_ticket(client, auth_headers, mid)
    client.get(f"/maintenances/{mid}/worksheet", headers=auth_headers)
    ws = db_session.query(Worksheet).filter(
        Worksheet.maintenance_id == uuid.UUID(mid)
    ).first()
    assert ws is not None and not ws.closed

    response = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert response.status_code == 409


def test_sign_maintenance_idempotent_when_already_signed(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_weekday_started_maintenance(client, auth_headers)
    _save_and_close_ticket(client, auth_headers, mid)
    _mark_worksheet_pdf_generated(client, auth_headers, db_session, mid)

    first = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert first.status_code == 200, first.text
    second = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert second.status_code == 200, second.text


def test_sign_maintenance_not_found(
    client: TestClient, auth_headers: dict,
) -> None:
    response = client.post(
        "/maintenances/00000000-0000-7000-8000-000000000099/sign",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_sign_maintenance_forbidden_ownership(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_user: dict, test_market: Market, test_equipment: Equipment,
    test_technician: Technician,
) -> None:
    other = FSMUser(
        email="other-technician@example.com",
        user_name="Other Technician",
        passwd=hash_password("password123"),
        user_role="TECHNICIAN",
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    other_tech = Technician(user_id=other.user_id)
    db_session.add(other_tech)
    db_session.commit()
    db_session.refresh(other_tech)

    ticket = Ticket(
        ticket_date=datetime.fromisoformat(_WEEKDAY),
        ticket_description="Other technician's ticket",
        priority="NORMAL",
        status="CLOSED",
        market_id=test_market.market_id,
        equipment_id=test_equipment.equipment_id,
        assigned_to=other_tech.technician_id,
        created_by=other.user_id,
        updated_by=other.user_id,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)

    maintenance = Maintenance(
        ticket_id=ticket.ticket_id,
        maintenance_date=datetime.fromisoformat(_WEEKDAY),
        created_by=other.user_id,
        updated_by=other.user_id,
    )
    db_session.add(maintenance)
    db_session.commit()
    db_session.refresh(maintenance)

    db_session.add(Worksheet(
        maintenance_id=maintenance.maintenance_id,
        closed=True,
        pdf_path="tests/signed.pdf",
        sheet_number="WS-2026-000099",
    ))
    db_session.commit()

    response = client.post(
        f"/maintenances/{maintenance.maintenance_id}/sign",
        headers=auth_headers,
    )
    assert response.status_code == 403


# ── ticket_status on maintenance items (change: add-signed-ticket-status) ─────


def test_maintenance_item_includes_ticket_status(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_weekday_started_maintenance(client, auth_headers)

    item = client.get(f"/maintenances/{mid}", headers=auth_headers).json()
    assert item["ticket_status"] == "IN PROGRESS"

    listing = client.get("/maintenances", headers=auth_headers).json()
    match = [m for m in listing if m["maintenance_id"] == mid]
    assert match and match[0]["ticket_status"] == "IN PROGRESS"


def test_sign_response_includes_signed_ticket_status(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_weekday_started_maintenance(client, auth_headers)
    _save_and_close_ticket(client, auth_headers, mid)
    _mark_worksheet_pdf_generated(client, auth_headers, db_session, mid)

    sign_resp = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert sign_resp.status_code == 200, sign_resp.text
    assert sign_resp.json()["ticket_status"] == "SIGNED"

    item = client.get(f"/maintenances/{mid}", headers=auth_headers).json()
    assert item["ticket_status"] == "SIGNED"
