from datetime import date, datetime
from types import SimpleNamespace

import structlog

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.utils.dates import get_holidays

import app.repositories.ticket_repo as ticket_repo

from app.models.ticket import Ticket
from app.models.maintenance import Maintenance, Pause
from app.models.master import Technician
from app.models.cancellation import Cancellation

from app.schemas.user import CurrentUser, UserRole
from app.schemas.ticket import AssignRequest, TicketStatus
from app.schemas.cancellation import CancellationRequest

# from app.services.maintenance_service import create_new_maintenance
from app.services.cancellation_service import create_new_cancellation

import app.repositories.maintenance_repo as maintenance_repo
import app.services.maintenance_service as maintenance_service

from app.core.utils.dates import get_holidays
from app.core.settings import settings
from app.core.storage import delete_object


_log = structlog.get_logger()


VALID_TRANSITIONS = {
    TicketStatus.open: [TicketStatus.assigned, TicketStatus.cancelled],
    TicketStatus.assigned: [TicketStatus.in_progress, TicketStatus.cancelled, TicketStatus.open],
    TicketStatus.in_progress: [TicketStatus.paused, TicketStatus.closed, TicketStatus.cancelled],
    TicketStatus.paused: [TicketStatus.in_progress, TicketStatus.cancelled],
    TicketStatus.cancelled: [],
    TicketStatus.closed: [TicketStatus.signed],
    TicketStatus.signed: []
}
  
def create_new_ticket(db, data, current_user):
    ticket = ticket_repo.save_ticket(db, data, current_user)
    ticket = ticket_repo.get_ticket_by_id(db, ticket.ticket_id, current_user)
    return _serialize_ticket_item(ticket)

def get_ticket(db: Session, ticket_id: int, current_user):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)
    return _serialize_ticket_item(ticket)
    
def list_tickets(db, current_user, page: int = 1, page_size: int = 50):
    tickets_list = ticket_repo.get_visible_tickets(db, current_user, page, page_size)
    return list(map(_serialize_ticket_item, tickets_list))
  
# ── a. Start maintenance (new -> IN PROGRESS) ────────────────────────────────────
def start_maintenance(ticket_id: int, payload: None,
                 current_user, db: Session):
    """Idempotent, transactional start.

    - If a maintenance already exists for the ticket, return it (resume).
    - Otherwise create it in the SAME transaction as the ticket status
      transition: ticket status is never committed before the insert succeeds.
    - Concurrent double-calls are resolved by the DB unique constraint on
      maintenance.ticket_id: the loser flush-raises IntegrityError, rolls
      back, re-fetches and returns the winner's row.
    """
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)

    existing = maintenance_repo.get_maintenance_by_ticket(db, ticket_id)
    if existing is not None:
        return maintenance_service._serialize_maintenance_item(existing)

    validate_transition(ticket.status, TicketStatus.in_progress)

    data = SimpleNamespace(ticket_id=ticket_id, maintenance_date=datetime.now(), **(payload.model_dump() if payload else {}))
    ticket.status = TicketStatus.in_progress
    try:
        # No commit inside the repo: single atomic commit below.
        maintenance = maintenance_repo.create_maintenance(db, data, current_user, commit=False)
        db.commit()
    except IntegrityError:
        # Lost a race against a concurrent start: discard everything
        # (status change included) and return the winner's maintenance.
        db.rollback()
        maintenance = maintenance_repo.get_maintenance_by_ticket(db, ticket_id)
        if maintenance is None:
            raise HTTPException(409, "Maintenance creation conflicted, retry")
    return maintenance_service._serialize_maintenance_item(maintenance)


# ── b. Technician assignment ──────────────────────────────────────────────────────
def _get_technician_id_by_user(db, current_user):
    technician = db.query(Technician).filter(
        Technician.user_id == current_user.user_id
    ).first()
    if not technician:
        raise HTTPException(404, "Your ticket has not associated technician")
    return technician.technician_id if technician else None

def assign_ticket(ticket_id: int, payload: AssignRequest,
                  current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)

    if current_user.user_role not in ["TECHNICIAN", "DIRECTOR"]:
        raise HTTPException(400, "This role is not allowed to assign ticket")

    if current_user.user_role == "DIRECTOR" and payload.technician_id is None:
        # Director undo: clear the assignment and revert to OPEN.
        validate_transition(ticket.status, TicketStatus.open)
        ticket.status = TicketStatus.open
        ticket.assigned_to = None
        db.commit()
        return _serialize_ticket_item(ticket)

    validate_transition(ticket.status, TicketStatus.assigned)
    
    technician_id = _get_technician_id_by_user(db, current_user)

    if payload.technician_id and current_user.user_role == "DIRECTOR":
        technician_id = payload.technician_id

    ticket.status = TicketStatus.assigned
    ticket.assigned_to = technician_id
    db.commit()
    return _serialize_ticket_item(ticket)

# ── c. Cancel ───────────────────────────────────────────────────────────────
def cancel_ticket(ticket_id: int, payload: CancellationRequest,
                  current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)

    validate_transition(ticket.status, TicketStatus.cancelled)

    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump())
    ticket.status = TicketStatus.cancelled
    db.commit()
    create_new_cancellation(db, data, current_user)
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    return _serialize_ticket_item(ticket)
    
# ── c. Pause ───────────────────────────────────────────────────────────────
# Now in maintenance_service.py

# ── d. AddWkd ───────────────────────────────────────────────────────────────
def create_new_add_wkd(ticket_id: int, payload: None,
                 current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)

    maintenance = db.query(Maintenance).filter(Maintenance.ticket_id == ticket_id).first()
    # TODO: manage not maintenance ...
    
    ticket_date = ticket.ticket_date
    is_wkd_ticket = ticket_date.weekday() >= 5 or ticket_date in get_holidays(settings.country_company)
    if not is_wkd_ticket:
        raise HTTPException(403, "Ticket is neither weekend ticket or holiday ticket")
    
    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump())
    ticket_repo.save_add_wkd(db, data, current_user)

    last_pause = (
        db.query(Pause)
        .filter(Pause.maintenance_id == maintenance.maintenance_id)
        .order_by(Pause.created_at.desc())
        .first()
    )
    is_paused = last_pause and (not maintenance.updated_at or last_pause.created_at > maintenance.updated_at)
    new_status = TicketStatus.paused if is_paused else TicketStatus.closed

    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user)
    ticket.status = new_status
    db.commit()
    return _serialize_ticket_item(ticket)

# ── e. Delete ───────────────────────────────────────────────────────────────
def delete_ticket(ticket_id: int, current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)
    
    return ticket_repo.delete_ticket_by_id(db, ticket, current_user)

# ── f. Reset ────────────────────────────────────────────────────────────────
def reset_ticket(ticket_id: int, current_user, db: Session):
    """Reset a ticket to a fresh OPEN state, removing all its maintenance data.

    Only tickets that are neither OPEN (already fresh) nor SIGNED (finalized,
    must not be erased) can be reset. The status returns to `OPEN` but the
    assigned technician is preserved — the assignment is not a maintenance side
    effect and must survive the reset. The linked rows are deleted children-first
    (technicians, spares, pauses, photos, worksheet, maintenance) and, for a
    cancelled ticket, the cancellation record. The DB cleanup and the ticket
    status transition commit atomically; MinIO object removal (initial photo,
    working photos, worksheet PDF) is best-effort after the commit — failures
    are logged, never blocking the reset.
    """
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user, db)

    if ticket.status in (TicketStatus.open, TicketStatus.signed):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {ticket.status} → {TicketStatus.open}",
        )

    object_paths = maintenance_repo.delete_maintenance_by_ticket(db, ticket_id)

    db.query(Cancellation).filter(
        Cancellation.ticket_id == ticket_id
    ).delete(synchronize_session=False)

    ticket.status = TicketStatus.open
    db.commit()

    for object_path in object_paths:
        try:
            delete_object(object_path)
        except Exception as error:
            _log.error(
                "ticket_reset_object_delete_failed",
                ticket_id=ticket_id,
                object_path=object_path,
                error=str(error),
            )

    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user)
    return _serialize_ticket_item(ticket)

    
# ── Helpers ───────────────────────────────────────────────────────────────
def assert_ownership(tk: Ticket, current_user: CurrentUser, db: Session):
    if tk.assigned_to is None or current_user.user_role == UserRole.director:
        return
    technician = db.query(Technician).filter(Technician.user_id == current_user.user_id).first()
    if technician and tk.assigned_to != technician.technician_id:
        raise HTTPException(403, "Forbidden")

def validate_transition(current_state: str, new_state: str):
    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current_state} → {new_state}"
        )

def _serialize_ticket_item(ticket: Ticket):
    columns = {c.name: getattr(ticket, c.name) for c in ticket.__table__.columns}
    if isinstance(columns.get("ticket_date"), datetime):
        columns["ticket_date"] = columns["ticket_date"].date()
    return SimpleNamespace(**columns,
                           market_name=ticket.market.market_name if ticket.market else None,
                           market_city=ticket.market.city if ticket.market else None,
                           equipment_name=ticket.equipment.equipment_name if ticket.equipment else None,
                           # cancellation_reason=ticket.cancellation.reason if ticket.cancellation else None,
                           assigned_name=ticket.technician.fsm_user.user_name if ticket.technician and ticket.technician.fsm_user else None
                    )