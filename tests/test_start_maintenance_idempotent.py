"""Idempotent, transactional start + by-ticket lookup contract tests.

Covers OpenSpec change `resume-maintenance-on-start`:
- PATCH /tickets/{ticket_id}/start returns MaintenanceItemResponse,
  creates with 201, resumes with 200, and is atomic (ticket status is
  never committed before the maintenance insert succeeds).
- GET /maintenances/by-ticket/{ticket_id} returns 200/404.
- MaintenanceItemResponse exposes maintenance_date and a nullable
  maintenance_description.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.repositories.maintenance_repo as maintenance_repo
import app.services.ticket_service as ticket_service
from app.models.maintenance import Maintenance
from app.models.ticket import Ticket


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket description",
    "priority": "NORMAL",
    "status": "OPEN",
    "market_id": 1,
    "equipment_id": 1,
}


def _create_assigned_ticket(client: TestClient, auth_headers: dict) -> int:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    assert create_resp.status_code == 201, create_resp.text
    ticket_id = create_resp.json()["ticket_id"]
    assign_resp = client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    assert assign_resp.status_code == 200, assign_resp.text
    return ticket_id


def _seed_ticket(
    db_session: Session,
    test_user: dict,
    test_market,
    test_equipment,
    status: str,
    assigned_to=None,
) -> Ticket:
    ticket = Ticket(
        ticket_date=datetime.now(),
        ticket_description="Seeded ticket",
        priority="NORMAL",
        status=status,
        market_id=test_market.market_id,
        equipment_id=test_equipment.equipment_id,
        assigned_to=assigned_to,
        created_by=test_user["user_id"],
        updated_by=test_user["user_id"],
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


# ── 1.1 Start creates with 201 / resumes with 200 ──────────────────────────────


def test_start_creates_with_201_when_no_maintenance_exists(
    client: TestClient, auth_headers: dict, test_market, test_equipment, test_technician
) -> None:
    ticket_id = _create_assigned_ticket(client, auth_headers)
    response = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["maintenance_id"]
    assert data["ticket_id"] == ticket_id
    assert "maintenance_date" in data
    assert "maintenance_description" in data


def test_start_twice_returns_existing_with_200_and_no_duplicate(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market, test_equipment, test_technician
) -> None:
    ticket_id = _create_assigned_ticket(client, auth_headers)
    first = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert first.status_code == 201, first.text

    second = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()["maintenance_id"] == first.json()["maintenance_id"]

    duplicates = (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket_id)
        .count()
    )
    assert duplicates == 1


# ── 1.2 By-ticket lookup ───────────────────────────────────────────────────────


def test_by_ticket_lookup_found(
    client: TestClient, auth_headers: dict, test_market, test_equipment, test_technician
) -> None:
    ticket_id = _create_assigned_ticket(client, auth_headers)
    start = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    maintenance_id = start.json()["maintenance_id"]

    response = client.get(f"/maintenances/by-ticket/{ticket_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["maintenance_id"] == maintenance_id
    assert data["ticket_id"] == ticket_id


def test_by_ticket_lookup_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/maintenances/by-ticket/999999", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Maintenance not found"


# ── 1.3 Schema enrichment ──────────────────────────────────────────────────────


def test_maintenance_item_response_includes_date_and_description(
    client: TestClient, auth_headers: dict, test_market, test_equipment, test_technician
) -> None:
    ticket_id = _create_assigned_ticket(client, auth_headers)
    start = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    maintenance_id = start.json()["maintenance_id"]

    response = client.get(f"/maintenances/{maintenance_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "maintenance_date" in data
    assert "maintenance_description" in data
    assert data["maintenance_description"] is None  # nullable until saved


# ── 1.5a Atomicity: ticket status never committed before the insert ────────────


def test_start_is_atomic_when_creation_fails(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market, test_equipment, test_technician, monkeypatch
) -> None:
    ticket_id = _create_assigned_ticket(client, auth_headers)

    def boom(db, data, current_user, **kwargs):
        raise RuntimeError("simulated maintenance insert failure")

    monkeypatch.setattr(maintenance_repo, "create_maintenance", boom)

    with pytest.raises(RuntimeError):
        client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)

    ticket = db_session.query(Ticket).filter(Ticket.ticket_id == ticket_id).one()
    assert ticket.status == "ASSIGNED"  # rolled back, never IN PROGRESS
    remaining = (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket_id)
        .count()
    )
    assert remaining == 0


# ── 1.5b + 1.5c Concurrent creation: loser recovers the winner's row ───────────


def test_integrity_error_recovery_returns_winner_row(
    db_session: Session, test_user: dict, test_technician,
    test_market, test_equipment, monkeypatch
) -> None:
    ticket = _seed_ticket(
        db_session, test_user, test_market, test_equipment,
        status="ASSIGNED", assigned_to=test_technician.technician_id,
    )

    # Winner row committed "concurrently" before the loser reaches flush.
    winner = Maintenance(
        ticket_id=ticket.ticket_id,
        maintenance_date=datetime.now(),
        created_by=test_user["user_id"],
        updated_by=test_user["user_id"],
    )
    db_session.add(winner)
    db_session.commit()
    db_session.refresh(winner)

    # First existence check misses the winner (lost race), second finds it.
    real_get_by_ticket = maintenance_repo.get_maintenance_by_ticket
    calls = {"n": 0}

    def fake_get_by_ticket(db, ticket_id_arg):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_get_by_ticket(db, ticket_id_arg)

    monkeypatch.setattr(maintenance_repo, "get_maintenance_by_ticket", fake_get_by_ticket)

    current_user = SimpleNamespace(user_id=test_user["user_id"], user_role="TECHNICIAN")
    result = ticket_service.start_maintenance(ticket.ticket_id, None, current_user, db_session)

    assert str(result.maintenance_id) == str(winner.maintenance_id)
    duplicates = (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket.ticket_id)
        .count()
    )
    assert duplicates == 1


# ── 1.5d Status transition matrix for start ────────────────────────────────────


@pytest.mark.parametrize(
    "status, expected_status_code",
    [
        # OPEN -> IN PROGRESS is not a legal direct transition: the client
        # must PATCH /assign first (assign-then-start coordinated flow).
        ("OPEN", 422),
        # Fresh creation path (no maintenance exists yet)
        ("ASSIGNED", 201),
        # PAUSED -> IN PROGRESS is a legal transition (pause/resume cycle);
        # with no maintenance row seeded, start creates one.
        ("PAUSED", 201),
        # Terminal or inconsistent states are rejected
        ("IN PROGRESS", 422),
        ("CLOSED", 422),
        ("CANCELLED", 422),
    ],
)
def test_start_status_transition_matrix(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_user: dict, test_technician, test_market, test_equipment,
    status: str, expected_status_code: int
) -> None:
    assigned_to = test_technician.technician_id if status != "OPEN" else None
    ticket = _seed_ticket(
        db_session, test_user, test_market, test_equipment,
        status=status, assigned_to=assigned_to,
    )
    response = client.patch(f"/tickets/{ticket.ticket_id}/start", headers=auth_headers)
    assert response.status_code == expected_status_code, response.text
