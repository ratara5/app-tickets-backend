import json
import uuid

import pytest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.master import Market, Equipment, Technician
from app.models.ticket import Ticket
from app.models.maintenance import Maintenance, Pause
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
) -> tuple[int, str]:
    """Start a ticket and return (ticket_id, maintenance_id).

    Starting a ticket creates its maintenance in the same transaction, so the
    maintenance already exists before any test can call POST /maintenances.
    These tests used to create a second one and then reference a hardcoded
    maintenance_id, but create_maintenance ignores a client-supplied id (the
    primary key comes from a uuid7 default), so the id they went on to use was
    never stored and the insert was rejected as a duplicate ticket_id.
    """
    resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    return ticket_id, resp.json()["maintenance_id"]


# A well-formed v7 that does not exist. Every maintenance id in this app is a
# UUID7, and the route binds it as UUID7, so a nil UUID (or any non-v7) is
# rejected at the path boundary with 422 before the handler ever runs. "Not
# found" therefore has to be asked with a real v7 shape.
_ABSENT_UUID7 = "0190f3a2-0000-7000-8000-000000000099"


def _create_ticket(client: TestClient, auth_headers: dict) -> int:
    """Create a ticket without starting it, so no maintenance exists yet."""
    resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    return resp.json()["ticket_id"]


def test_create_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """The standalone POST path still creates a maintenance.

    This deliberately uses a ticket that was never started: the start path
    creates its own maintenance, so starting first would make this a duplicate.
    """
    ticket_id = _create_ticket(client, auth_headers)
    response = client.post(
        "/maintenances",
        json={
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
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    assert maintenance_id, "starting the ticket must yield a maintenance"
    response = client.get(f"/maintenances/{maintenance_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["maintenance_id"] == maintenance_id
    assert response.json()["ticket_id"] == ticket_id


def test_get_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get(
        f"/maintenances/{_ABSENT_UUID7}",
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
        f"/maintenances/{_ABSENT_UUID7}",
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


def test_update_maintenance_new_pause_marks_ticket_paused_when_updated_at_bumped_after(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician, db_session: Session,
) -> None:
    """Regression: the first save introducing a pause must mark the owning ticket
    PAUSED even when a mid-form maintenance-row write (initial-photo chunked
    upload) bumped `updated_at` to AFTER the pause's device `created_at`.

    Previously `real_mark_as` classified PAUSED only when
    `newest_pause.created_at > maintenance.updated_at`; the upload bump makes
    that comparison false, so the very save that added the pause closed the
    ticket instead of pausing it.
    """
    resp = client.post(
        "/tickets",
        json={**TICKET_PAYLOAD, "ticket_date": "2026-09-22"},
        headers=auth_headers,
    )
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    start_resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert start_resp.status_code == 201
    maintenance_id = start_resp.json()["maintenance_id"]

    # Simulate the mid-form initial-photo upload: `complete_upload` writes
    # initial_photo_path to the maintenance row and commits, bumping updated_at
    # to a moment AFTER the pause the form is about to add.
    maintenance_row = db_session.query(Maintenance).filter(
        Maintenance.maintenance_id == uuid.UUID(maintenance_id)
    ).one()
    maintenance_row.initial_photo_path = "s3://mid-form-initial-photo.jpg"
    db_session.commit()
    db_session.refresh(maintenance_row)
    assert maintenance_row.updated_at is not None

    pause_created_at = "2026-09-22T09:00:00.000Z"  # device time, before the bump
    payload = {
        "maintenance_description": "Updated",
        "pauses": [{"pause_reason": "Awaiting part", "created_at": pause_created_at}],
    }

    first = client.patch(
        f"/maintenances/{maintenance_id}",
        data={"payload": json.dumps(payload)},
        headers=auth_headers,
    )
    assert first.status_code == 200
    assert first.json()["ticket_status"] == "PAUSED"

    ticket_row = db_session.query(Ticket).filter(Ticket.ticket_id == ticket_id).one()
    assert ticket_row.status == "PAUSED"

    # Designed lifecycle: re-saving the identical pause list (pause ->
    # continue -> save) with no new pause rolls the ticket to CLOSED.
    second = client.patch(
        f"/maintenances/{maintenance_id}",
        data={"payload": json.dumps(payload)},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["ticket_status"] == "CLOSED"
    db_session.refresh(ticket_row)
    assert ticket_row.status == "CLOSED"


# Pausing is a first-class endpoint: PATCH /maintenances/{id}/pause.
# It appends a pauses row and drives the owning ticket to PAUSED in one commit.
# There is no `status` on a maintenance — the assertion is on `ticket_status`,
# the owning ticket's status, which is the only place a pause is observable.


def test_pause_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    response = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Test pause"},
        headers=auth_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ticket_status"] == "PAUSED"
    assert [p["pause_reason"] for p in data["pauses"]] == ["Test pause"]


def test_pause_maintenance_persists_the_reason(
    client: TestClient, auth_headers: dict, db_session: Session, test_user: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """The pause row is stored, not just echoed: the reason, a time and the author."""
    _ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    response = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Awaiting part"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text

    rows = db_session.query(Pause).filter(
        Pause.maintenance_id == uuid.UUID(maintenance_id)
    ).all()
    assert len(rows) == 1
    assert rows[0].pause_reason == "Awaiting part"
    assert rows[0].created_at is not None
    assert rows[0].created_by == test_user["user_id"]


def test_pause_maintenance_appends_to_existing_pauses(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """Pausing is an append, never a replace: the earlier pauses are kept.

    PATCH /maintenances/{id} replaces the whole pause list because the mobile
    form re-sends it. The pause endpoint expresses "pause now" and has no
    opinion about history, so it must not drop what is already there.
    """
    _ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    for reason in ("Awaiting part", "Site closed"):
        response = client.patch(
            f"/maintenances/{maintenance_id}/pause",
            json={"pause_reason": reason},
            headers=auth_headers,
        )
        # The second call is the idempotent-retry case, so it adds no row.
        assert response.status_code == 200, response.text

    pauses = response.json()["pauses"]
    assert [p["pause_reason"] for p in pauses] == ["Awaiting part"], (
        "re-pausing must not append a duplicate row for the same PAUSED state"
    )


def test_pause_maintenance_is_idempotent_when_already_paused(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """A second pause returns 200 with the same state, not a 409."""
    _ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    first = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Awaiting part"},
        headers=auth_headers,
    )
    second = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Awaiting part"},
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["ticket_status"] == "PAUSED"
    assert second.json()["pauses"] == first.json()["pauses"]


def test_pause_maintenance_requires_a_reason(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    _ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    response = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_pause_maintenance_rejects_a_closed_ticket(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """Only IN PROGRESS may be paused; a CLOSED maintenance is 422, not 409."""
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
    ticket_row = db_session.query(Ticket).filter(Ticket.ticket_id == ticket_id).one()
    ticket_row.status = "CLOSED"
    db_session.commit()

    response = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Too late"},
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text
    db_session.refresh(ticket_row)
    assert ticket_row.status == "CLOSED", "a rejected pause must not move the ticket"


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
    # `_ABSENT_UUID7`, not a nil UUID: a nil id is not a v7, so the route's path
    # binding rejects it with 422 before the handler can answer 404. While the
    # route did not exist at all, this test 404'd for the wrong reason and the
    # wrong id shape hid that.
    response = client.patch(
        f"/maintenances/{_ABSENT_UUID7}/pause",
        json={"pause_reason": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_pause_maintenance_commits_the_pause_and_the_status_once(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """The pause row and the ticket's PAUSED status must be ONE transaction.

    Two commits would leave a window where a maintenance carries a pause the
    ticket has not accepted, and where a failure after the first commit orphans
    the pause row entirely. Counting commits is the only way to catch that here:
    the happy path looks identical either way, and a failed second commit is not
    something the HTTP surface can express.
    """
    from sqlalchemy.orm import Session as OrmSession

    _ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)

    commits: list[int] = []

    def _count_commit(_session) -> None:
        commits.append(1)

    # Class-level listener, because the route runs on its own session from the
    # get_db override, not on the `db_session` this test would see. Only the
    # window around the request is counted, so the setup commits are excluded.
    # Note: an engine-level "commit" event does NOT fire for `Session.commit()`
    # in SQLAlchemy 2.0 — that only fires for `engine.commit()` — so it silently
    # counts zero and the test would fail against correct code.
    event.listen(OrmSession, "after_commit", _count_commit)
    try:
        response = client.patch(
            f"/maintenances/{maintenance_id}/pause",
            json={"pause_reason": "Awaiting part"},
            headers=auth_headers,
        )
    finally:
        event.remove(OrmSession, "after_commit", _count_commit)

    assert response.status_code == 200, response.text
    assert len(commits) == 1, f"expected 1 commit, got {len(commits)}"


def test_pause_maintenance_forbidden_for_other_technician(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    """A technician who is not the ticket's assignee gets 403, not a silent pause.

    Same shape as test_sign_maintenance_forbidden_ownership: the maintenance
    belongs to a different technician, and the caller is `test_user`.
    """
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
        status="IN PROGRESS",
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

    response = client.patch(
        f"/maintenances/{maintenance.maintenance_id}/pause",
        json={"pause_reason": "Not mine"},
        headers=auth_headers,
    )
    assert response.status_code == 403, response.text
    assert db_session.query(Pause).filter(
        Pause.maintenance_id == maintenance.maintenance_id
    ).count() == 0, "a refused pause must not leave a row behind"


def test_delete_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
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
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
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
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
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
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
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
    ticket_id, maintenance_id = _create_assigned_started_ticket(client, auth_headers)
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


def test_sign_maintenance_does_not_require_generated_pdf(
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

    # Signing is tied to the worksheet save, not to PDF generation, so an
    # ungenerated PDF is not a conflict.
    response = client.post(f"/maintenances/{mid}/sign", headers=auth_headers)
    assert response.status_code == 200


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
