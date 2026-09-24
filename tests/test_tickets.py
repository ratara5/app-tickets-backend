from datetime import datetime

import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.core.security import hash_password
from app.models.fsm_user import FSMUser
from app.models.master import Market, Equipment, Technician
from app.models.ticket import Ticket
from app.schemas.ticket import TicketStatus
from app.services.ticket_service import VALID_TRANSITIONS, validate_transition


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket description",
    "priority": "NORMAL",
    "status": "OPEN",
    "market_id": 1,
    "equipment_id": 1,
}

# Fixed Saturday (2026-08-01) so WKD-only tests do not depend on the run date.
WEEKEND_TICKET_DATE = "2026-08-01T00:00:00"


def test_create_ticket_success(
    client: TestClient, auth_headers: dict, test_market: Market, test_equipment: Equipment
) -> None:
    response = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["ticket_description"] == "Test ticket description"


def test_create_ticket_unauthorized(client: TestClient) -> None:
    response = client.post("/tickets", json=TICKET_PAYLOAD)
    assert response.status_code == 401


def test_create_ticket_invalid_data(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post("/tickets", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_list_tickets(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/tickets", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_tickets_unauthorized(client: TestClient) -> None:
    response = client.get("/tickets")
    assert response.status_code == 401


def _login(client: TestClient, email: str, password: str = "password123") -> dict:
    response = client.post("/auth/login", json={"email": email, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_role_user(db: Session, role: str, email: str, tech_user_id: int = -1):
    user = FSMUser(
        email=email,
        user_name=f"Role {role}",
        passwd=hash_password("password123"),
        user_role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    technician = Technician(user_id=user.user_id)
    db.add(technician)
    db.commit()
    db.refresh(technician)
    return user, technician


def _seed_visible_ticket(
    db: Session,
    market: Market,
    equipment: Equipment,
    author_id: int,
    tech_id: int | None,
    status: str = "OPEN",
    ticket_id_suffix: str = "",
) -> Ticket:
    ticket = Ticket(
        ticket_date=datetime.now(),
        ticket_description=f"Visibility ticket {ticket_id_suffix}",
        priority="NORMAL",
        status=status,
        market_id=market.market_id,
        equipment_id=equipment.equipment_id,
        assigned_to=tech_id,
        created_by=author_id,
        updated_by=author_id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_list_tickets_director_sees_all_tickets_in_date_window(
    client: TestClient, db_session: Session,
    test_market: Market, test_equipment: Equipment,
) -> None:
    director, director_tech = _create_role_user(db_session, "DIRECTOR", "director@example.com")
    other, other_tech = _create_role_user(db_session, "TECHNICIAN", "other@example.com")
    unassigned = _seed_visible_ticket(db_session, test_market, test_equipment, director.user_id, None, ticket_id_suffix="u")
    assigned_to_director = _seed_visible_ticket(db_session, test_market, test_equipment, director.user_id, director_tech.technician_id, ticket_id_suffix="d")
    assigned_to_other = _seed_visible_ticket(db_session, test_market, test_equipment, other.user_id, other_tech.technician_id, ticket_id_suffix="o")
    cancelled = _seed_visible_ticket(db_session, test_market, test_equipment, other.user_id, other_tech.technician_id, status="CANCELLED", ticket_id_suffix="x")

    response = client.get("/tickets", headers=_login(client, "director@example.com"))
    assert response.status_code == 200
    returned_ids = {item["ticket_id"] for item in response.json()}
    assert returned_ids == {
        unassigned.ticket_id,
        assigned_to_director.ticket_id,
        assigned_to_other.ticket_id,
        cancelled.ticket_id,
    }


def test_list_tickets_technician_only_sees_self_and_unassigned(
    client: TestClient, db_session: Session,
    test_market: Market, test_equipment: Equipment,
) -> None:
    director, director_tech = _create_role_user(db_session, "DIRECTOR", "director@example.com")
    other, other_tech = _create_role_user(db_session, "TECHNICIAN", "other@example.com")
    unassigned = _seed_visible_ticket(db_session, test_market, test_equipment, director.user_id, None, ticket_id_suffix="u")
    assigned_to_other = _seed_visible_ticket(db_session, test_market, test_equipment, other.user_id, other_tech.technician_id, ticket_id_suffix="o")
    cancel_to_other = _seed_visible_ticket(db_session, test_market, test_equipment, other.user_id, other_tech.technician_id, status="CANCELLED", ticket_id_suffix="c")

    response = client.get("/tickets", headers=_login(client, "other@example.com"))
    assert response.status_code == 200
    returned_ids = {item["ticket_id"] for item in response.json()}
    assert returned_ids == {unassigned.ticket_id, assigned_to_other.ticket_id}
    assert cancel_to_other.ticket_id not in returned_ids


def test_get_ticket_success(
    client: TestClient, auth_headers: dict, test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.get(f"/tickets/{ticket_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["ticket_id"] == ticket_id


def test_get_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/tickets/99999", headers=auth_headers)
    assert response.status_code == 404


def test_get_ticket_unauthorized(client: TestClient) -> None:
    response = client.get("/tickets/1")
    assert response.status_code == 401


def test_assign_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.patch(
        f"/tickets/{ticket_id}/assign",
        json={"technician_id": test_technician.technician_id},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ASSIGNED"


def test_assign_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.patch("/tickets/1/assign", json={})
    assert response.status_code == 401


def test_assign_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/tickets/99999/assign",
        json={},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_assign_ticket_invalid_state(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    response = client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    assert response.status_code in (400, 422)


def test_assign_ticket_director_assigns_concrete_technician(
    client: TestClient, db_session: Session,
    test_market: Market, test_equipment: Equipment,
) -> None:
    director, _ = _create_role_user(db_session, "DIRECTOR", "director-assign@example.com")
    tech, tech_record = _create_role_user(db_session, "TECHNICIAN", "tech-assign@example.com")
    ticket = _seed_visible_ticket(
        db_session, test_market, test_equipment,
        author_id=director.user_id, tech_id=None, status="OPEN", ticket_id_suffix="assign",
    )

    response = client.patch(
        f"/tickets/{ticket.ticket_id}/assign",
        json={"technician_id": tech_record.technician_id},
        headers=_login(client, "director-assign@example.com"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ASSIGNED"
    db_session.refresh(ticket)
    assert ticket.assigned_to == tech_record.technician_id


def test_assign_ticket_director_undo_via_null_technician(
    client: TestClient, db_session: Session,
    test_market: Market, test_equipment: Equipment,
) -> None:
    director, _ = _create_role_user(db_session, "DIRECTOR", "director-undo@example.com")
    tech, tech_record = _create_role_user(db_session, "TECHNICIAN", "tech-undo@example.com")
    ticket = _seed_visible_ticket(
        db_session, test_market, test_equipment,
        author_id=director.user_id, tech_id=tech_record.technician_id,
        status="ASSIGNED", ticket_id_suffix="undo",
    )

    response = client.patch(
        f"/tickets/{ticket.ticket_id}/assign",
        json={"technician_id": None},
        headers=_login(client, "director-undo@example.com"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OPEN"
    db_session.refresh(ticket)
    assert ticket.assigned_to is None


def test_assign_ticket_director_undo_rejected_on_work_started_ticket(
    client: TestClient, db_session: Session,
    test_market: Market, test_equipment: Equipment,
) -> None:
    director, _ = _create_role_user(db_session, "DIRECTOR", "director-undo-reject@example.com")
    tech, tech_record = _create_role_user(db_session, "TECHNICIAN", "tech-undo-reject@example.com")
    for status in ["OPEN", "IN_PROGRESS", "PAUSED", "CLOSED", "SIGNED", "CANCELLED"]:
        ticket = _seed_visible_ticket(
            db_session, test_market, test_equipment,
            author_id=director.user_id, tech_id=tech_record.technician_id,
            status=status, ticket_id_suffix=status.lower(),
        )
        response = client.patch(
            f"/tickets/{ticket.ticket_id}/assign",
            json={"technician_id": None},
            headers=_login(client, "director-undo-reject@example.com"),
        )
        assert response.status_code == 422, f"status {status} should reject undo"


def test_assign_ticket_technician_null_payload_keeps_self_assign(
    client: TestClient, db_session: Session,
    test_market: Market, test_equipment: Equipment,
) -> None:
    technician, tech_record = _create_role_user(db_session, "TECHNICIAN", "tech-null@example.com")
    ticket = _seed_visible_ticket(
        db_session, test_market, test_equipment,
        author_id=technician.user_id, tech_id=None, status="OPEN", ticket_id_suffix="null-self",
    )

    response = client.patch(
        f"/tickets/{ticket.ticket_id}/assign",
        json={"technician_id": None},
        headers=_login(client, "tech-null@example.com"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ASSIGNED"
    db_session.refresh(ticket)
    assert ticket.assigned_to == tech_record.technician_id


def test_start_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    response = client.patch(
        f"/tickets/{ticket_id}/start",
        headers=auth_headers
    )
    # Idempotent start contract: fresh creation returns 201 with the
    # enriched MaintenanceItemResponse shape.
    assert response.status_code == 201
    data = response.json()
    assert data["maintenance_id"]
    assert data["ticket_id"] == ticket_id
    assert "maintenance_date" in data
    assert "maintenance_description" in data


def test_start_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.patch("/tickets/1/start")
    assert response.status_code == 401


def test_start_ticket_invalid_state(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.patch(
        f"/tickets/{ticket_id}/start",
        headers=auth_headers
    )
    assert response.status_code in (400, 422)


def test_cancel_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.patch(
        f"/tickets/{ticket_id}/cancel",
        json={"cancellation_reason": "Test cancellation"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/tickets/1/cancel",
        json={"cancellation_reason": "Test"}
    )
    assert response.status_code == 401


def test_cancel_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/tickets/99999/cancel",
        json={"cancellation_reason": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_add_wkd_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    # WKD observations are only allowed on weekend/holiday tickets; use a fixed
    # Saturday so the test is deterministic regardless of the run date.
    create_resp = client.post(
        "/tickets",
        json={**TICKET_PAYLOAD, "ticket_date": WEEKEND_TICKET_DATE},
        headers=auth_headers,
    )
    ticket_id = create_resp.json()["ticket_id"]
    client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    client.patch(
        f"/tickets/{ticket_id}/start",
        headers=auth_headers
    )
    response = client.patch(
        f"/tickets/{ticket_id}/addwkd",
        json={
            "operation_percentage": 50,
            "market_temperature": 25,
            "operation_damage": False,
            "completed": False,
            "observations_wkd": "Test observations",
        },
        headers=auth_headers
    )
    assert response.status_code == 200


def test_add_wkd_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/tickets/1/addwkd",
        json={
            "operation_percentage": 50,
            "market_temperature": 25,
            "operation_damage": False,
            "completed": False,
            "observations_wkd": "Test",
        }
    )
    assert response.status_code == 401


def test_delete_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.delete(f"/tickets/{ticket_id}", headers=auth_headers)
    assert response.status_code == 204


def test_delete_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.delete("/tickets/1")
    assert response.status_code == 401


def test_delete_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.delete("/tickets/99999", headers=auth_headers)
    assert response.status_code == 404


# ── SIGNED ticket status (change: add-signed-ticket-status) ────────────────────


def test_ticket_status_exposes_signed_after_closed() -> None:
    statuses = list(TicketStatus)
    assert TicketStatus.signed == "SIGNED"
    assert statuses.index(TicketStatus.signed) == statuses.index(TicketStatus.closed) + 1


def test_valid_transitions_allow_closed_to_signed() -> None:
    assert VALID_TRANSITIONS[TicketStatus.closed] == [TicketStatus.signed]


def test_valid_transitions_signed_has_no_outgoing() -> None:
    assert VALID_TRANSITIONS[TicketStatus.signed] == []


def test_validate_transition_accepts_closed_to_signed() -> None:
    validate_transition(TicketStatus.closed, TicketStatus.signed)


def test_validate_transition_rejects_signed_as_source() -> None:
    for target in TicketStatus:
        with pytest.raises(HTTPException):
            validate_transition(TicketStatus.signed, target)


def test_validate_transition_rejects_non_closed_sources_to_signed() -> None:
    for source in TicketStatus:
        if source == TicketStatus.closed:
            continue
        with pytest.raises(HTTPException):
            validate_transition(source, TicketStatus.signed)
