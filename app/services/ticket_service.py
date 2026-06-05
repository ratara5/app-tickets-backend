from datetime import date
from types import SimpleNamespace

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core.utils.dates import get_holidays

import app.repositories.ticket_repo as ticket_repo

from app.models.ticket import Ticket
from app.models.maintenance import Maintenance
from app.models.master import Technician

from app.schemas.user import CurrentUser, UserRole
from app.schemas.ticket import AssignRequest, TicketStatus
from app.schemas.cancellation import CancellationRequest

# from app.services.maintenance_service import create_new_maintenance
from app.services.cancellation_service import create_new_cancellation

import app.repositories.maintenance_repo as maintenance_repo

from app.core.utils.dates import get_holidays
from app.core.settings import settings


VALID_TRANSITIONS = {
    TicketStatus.open: [TicketStatus.assigned, TicketStatus.cancelled],
    TicketStatus.assigned: [TicketStatus.in_progress, TicketStatus.cancelled],
    TicketStatus.in_progress: [TicketStatus.paused, TicketStatus.closed, TicketStatus.cancelled],
    TicketStatus.paused: [TicketStatus.in_progress, TicketStatus.cancelled],
    TicketStatus.cancelled: [],
    TicketStatus.closed: []
}
  
def create_new_ticket(db, data, current_user):
    return ticket_repo.save_ticket(db, data, current_user)

def get_ticket(db: Session, ticket_id: int, current_user):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user)
    return _serialize_ticket_item(ticket)
    
def list_tickets(db, current_user, page: int = 1, page_size: int = 50):
    tickets_list = ticket_repo.get_visible_tickets(db, current_user, page, page_size)
    return list(map(_serialize_ticket_item, tickets_list))
  
# ── a. Start maintenance (new -> IN PROGRESS) ────────────────────────────────────
def start_maintenance(ticket_id: int, payload: None,
                 current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user)

    validate_transition(ticket.status, TicketStatus.in_progress)
    
    # Validate hollidays/weekend: Not necessary here
    # ...

    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump() if payload else {})
    ticket.status = TicketStatus.in_progress
    db.commit()
    # create_new_maintenance(db, data, current_user)
    maintenance_repo.create_maintenance(db, data, current_user)
    return ticket

# ── b. Technician assignment ──────────────────────────────────────────────────────
def _get_technician_id_by_user(db, current_user):
    technician = db.query(Technician).filter(
        Technician.user_id == current_user.user_id
    ).first()
    if not technician:
        raise HTTPException(404, "Your ticket has not associated technician")
    return technician.id_technician if technician else None

def assign_ticket(ticket_id: int, payload: AssignRequest,
                  current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user)

    validate_transition(ticket.status, TicketStatus.assigned)

    if current_user.user_role not in ["TECHNICIAN", "DIRECTOR"]:
        raise HTTPException(400, "This role is not allowed to assign ticket")
    
    technician_id = _get_technician_id_by_user(db, current_user)

    if payload.technician_id and current_user.user_role == "DIRECTOR":
        technician_id = payload.technician_id

    ticket.status = TicketStatus.assigned
    ticket.assigned_to = technician_id
    db.commit()
    return ticket

# ── c. Cancel ───────────────────────────────────────────────────────────────
def cancel_ticket(ticket_id: int, payload: CancellationRequest,
                  current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user)

    validate_transition(ticket.status, TicketStatus.cancelled)

    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump())
    ticket.status = TicketStatus.cancelled
    db.commit()
    create_new_cancellation(db, data, current_user)
    return ticket
    
# ── c. Pause ───────────────────────────────────────────────────────────────
# Now in maintenance_service.py

# ── d. AddWkd ───────────────────────────────────────────────────────────────
def create_new_add_wkd(ticket_id: int, payload: None,
                 current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user)

    maintenance = db.query(Maintenance).filter(Maintenance.ticket_id == ticket_id).first()
    # TODO: manage not maintenance ...
    
    ticket_date = ticket.ticket_date
    is_wkd_ticket = ticket_date.weekday() >= 5 or ticket_date in get_holidays(settings.country_company)
    if not is_wkd_ticket:
        raise HTTPException(403, "Ticket is neither weekend ticket or holiday ticket")
    
    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump())
    ticket = ticket_repo.save_add_wkd(db, data, current_user)   

    if maintenance.real_mark_as == "PAUSED":
        ticket.status = TicketStatus.paused
    else:
        ticket.status = TicketStatus.closed

    return ticket

# ── e. Delete ───────────────────────────────────────────────────────────────
def delete_ticket(ticket_id: int, current_user, db: Session):
    ticket = ticket_repo.get_ticket_by_id(db, ticket_id, current_user) 
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    assert_ownership(ticket, current_user)
    
    return ticket_repo.delete_ticket_by_id(db, ticket, current_user)

    
# ── Helpers ───────────────────────────────────────────────────────────────
def assert_ownership(tk: Ticket, current_user: CurrentUser):
    if tk.assigned_to == "" or current_user.user_role == UserRole.director:
        return
    if tk.assigned_to != current_user.technician.technician_id:
        raise HTTPException(403, "Forbidden")

def validate_transition(current_state: str, new_state: str):
    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current_state} → {new_state}"
        )

def _serialize_ticket_item(ticket: Ticket):
    return SimpleNamespace(**ticket.model_dump(),
                           market_name=ticket.market.market_name if ticket.market else None,
                           market_city=ticket.market.market_city if ticket.market else None,
                           equipment_name=ticket.equipment.equipment_name if ticket.equipment else None,
                           # cancellation_reason=ticket.cancellation.reason if ticket.cancellation else None,
                           assigned_name=ticket.technician.fsm_user.user_name if ticket.technician and ticket.technician.fsm_user else None
                    )