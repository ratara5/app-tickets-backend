"""PATCH /tickets/{ticket_id}/reset contract tests.

Covers the `reset-ticket` change:
- Resetting an OPEN ticket is rejected (422) — a fresh ticket must not be erased.
- Resetting a SIGNED ticket is rejected (422) — a finalized ticket must not be erased.
- Resetting an allowed state returns the ticket to OPEN while PRESERVING the
  assigned technician and removes the linked maintenance rows (children first).
"""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.maintenance import Maintenance, MaintenanceTechnician, Pause
from app.models.photo import Photo
from app.models.ticket import Ticket
from app.models.worksheet import Worksheet


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
        ticket_description="Reset ticket",
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


def _seed_paused_ticket_with_maintenance(
    db_session: Session,
    test_user: dict,
    test_technician,
    test_market,
    test_equipment,
) -> Ticket:
    ticket = _seed_ticket(
        db_session, test_user, test_market, test_equipment,
        status="PAUSED", assigned_to=test_technician.technician_id,
    )

    maintenance = Maintenance(
        ticket_id=ticket.ticket_id,
        maintenance_date=datetime.now(),
        maintenance_description="Linked maintenance",
        initial_photo_path="maintenances/reset/initial.jpg",
        created_by=test_user["user_id"],
        updated_by=test_user["user_id"],
    )
    db_session.add(maintenance)
    db_session.commit()
    db_session.refresh(maintenance)

    db_session.add(MaintenanceTechnician(
        maintenance_id=maintenance.maintenance_id,
        technician_id=test_technician.technician_id,
        start_hour=datetime.now().time(),
        end_hour=datetime.now().time(),
        created_by=test_user["user_id"],
        updated_by=test_user["user_id"],
    ))
    db_session.add(Pause(
        maintenance_id=maintenance.maintenance_id,
        pause_reason="Seeded pause",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by=test_user["user_id"],
        updated_by=test_user["user_id"],
    ))
    db_session.commit()

    return ticket


def test_reset_used_ticket_with_photos_and_worksheet_removes_them(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_user: dict, test_technician, test_market, test_equipment,
) -> None:
    ticket = _seed_paused_ticket_with_maintenance(
        db_session, test_user, test_technician, test_market, test_equipment
    )
    maintenance = (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket.ticket_id)
        .one()
    )
    maintenance_id = maintenance.maintenance_id
    db_session.add_all([
        Photo(
            maintenance_id=maintenance_id,
            photo_path="maintenances/reset/photo-1.jpg",
            processed=True,
            created_by=test_user["user_id"],
            updated_by=test_user["user_id"],
        ),
        Photo(
            maintenance_id=maintenance_id,
            photo_path="maintenances/reset/photo-2.jpg",
            processed=True,
            created_by=test_user["user_id"],
            updated_by=test_user["user_id"],
        ),
        Worksheet(
            maintenance_id=maintenance_id,
            sheet_number="WK-RESET-00042",
            pdf_path="maintenances/reset/worksheet.pdf",
        ),
    ])
    db_session.commit()

    response = client.patch(
        f"/tickets/{ticket.ticket_id}/reset", headers=auth_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "OPEN"

    assert (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket.ticket_id)
        .count() == 0
    )
    assert (
        db_session.query(Photo)
        .filter(Photo.maintenance_id == maintenance_id)
        .count() == 0
    )
    assert (
        db_session.query(Worksheet)
        .filter(Worksheet.maintenance_id == maintenance_id)
        .count() == 0
    )


def test_reset_open_ticket_is_rejected(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_user: dict, test_market, test_equipment,
) -> None:
    ticket = _seed_ticket(
        db_session, test_user, test_market, test_equipment, status="OPEN"
    )

    response = client.patch(f"/tickets/{ticket.ticket_id}/reset", headers=auth_headers)

    assert response.status_code == 422, response.text
    assert "Invalid transition: OPEN" in response.json()["detail"]
    db_session.refresh(ticket)
    assert ticket.status == "OPEN"
    assert (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket.ticket_id)
        .count() == 0
    )


def test_reset_signed_ticket_is_rejected(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_user: dict, test_technician, test_market, test_equipment,
) -> None:
    ticket = _seed_ticket(
        db_session, test_user, test_market, test_equipment,
        status="SIGNED", assigned_to=test_technician.technician_id,
    )

    response = client.patch(f"/tickets/{ticket.ticket_id}/reset", headers=auth_headers)

    assert response.status_code == 422, response.text
    assert "Invalid transition: SIGNED" in response.json()["detail"]
    db_session.refresh(ticket)
    assert ticket.status == "SIGNED"
    assert ticket.assigned_to == test_technician.technician_id


def test_reset_used_ticket_returns_open_and_preserves_assignment(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_user: dict, test_technician, test_market, test_equipment,
) -> None:
    ticket = _seed_paused_ticket_with_maintenance(
        db_session, test_user, test_technician, test_market, test_equipment
    )
    assert (
        db_session.query(Maintenance)
        .filter(Maintenance.ticket_id == ticket.ticket_id)
        .count() == 1
    )

    response = client.patch(
        f"/tickets/{ticket.ticket_id}/reset", headers=auth_headers
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "OPEN"
    assert data["assigned_name"] == test_user["user_name"]

    db_session.refresh(ticket)
    assert ticket.status == "OPEN"
    assert ticket.assigned_to == test_technician.technician_id

    maintenance_ids = (
        db_session.query(Maintenance.maintenance_id)
        .filter(Maintenance.ticket_id == ticket.ticket_id)
        .all()
    )
    assert maintenance_ids == []
    assert (
        db_session.query(MaintenanceTechnician)
        .filter(MaintenanceTechnician.maintenance_id.in_(
            maintenance_ids if maintenance_ids else [None]
        ))
        .count() == 0
    )
    assert (
        db_session.query(Pause)
        .filter(Pause.maintenance_id.in_(
            maintenance_ids if maintenance_ids else [None]
        ))
        .count() == 0
    )