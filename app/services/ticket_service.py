from datetime import date
from types import SimpleNamespace

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.repositories.ticket_repo import save_ticket, get_visible_tickets

from app.models.ticket import Ticket
from app.models.master import Technician

from app.schemas.ticket import AssignRequest
from app.schemas.cancellation import CancellationRequest
from app.schemas.pause import PauseRequest

from app.services.maintenance_service import create_new_maintenance
from app.services.cancellation_service import create_new_cancellation
from app.services.pause_service import create_new_pause


def create_new_ticket(db, data, current_user):
    return save_ticket(db, data, current_user)

def list_tickets(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_tickets(db, current_user, page, page_size)

VALID_TRANSITIONS = {
    "OPEN": ["ASSIGNED", "CANCELLED"],
    "ASSIGNED": ["IN PROGRESS", "CANCELLED"],
    "IN PROGRESS": ["PAUSED", "CLOSED", "CANCELLED"],
    "PAUSED": ["IN PROGRESS", "CANCELLED"],
    "CANCELLED": [],
    "CLOSED": []
}

def _validate_transition(current_state: str, new_state: str):
    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current_state} → {new_state}"
        )
    
# ── a. Start maintenance (new -> IN PROGRESS) ────────────────────────────────────
def start_maintenance(ticket_id: int, payload: None,
                 current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    
    _validate_transition(ticket.status, "IN PROGRESS")
    
    # Validate hollidays/weekend: Not necessary
    # ...

    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump() if payload else {})
    ticket.status = "IN PROGRESS"
    db.commit()
    create_new_maintenance(db, data, current_user)
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
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    _validate_transition(ticket.status, "ASSIGNED")

    if current_user.user_role not in ["TECHNICIAN", "DIRECTOR"]:
        raise HTTPException(400, "This role is not allowed to assign ticket")
    
    technician_id = _get_technician_id_by_user(db, current_user)

    if payload.technician_id and current_user.user_role == "DIRECTOR":
        technician_id = payload.technician_id

    ticket.status = "ASSIGNED"
    ticket.assigned_to = technician_id
    db.commit()
    return ticket

# ── c. Cancel ───────────────────────────────────────────────────────────────
def cancel_ticket(ticket_id: int, payload: CancellationRequest,
                  current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    _validate_transition(ticket.status, "CANCELLED")

    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump())
    ticket.status = "CANCELLED"
    db.commit()
    create_new_cancellation(db, data, current_user)
    return ticket
    
# ── c. Pause ───────────────────────────────────────────────────────────────
def pause_ticket(ticket_id: int, payload: PauseRequest,
                  current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    _validate_transition(ticket.status, "PAUSED")

    data = SimpleNamespace(ticket_id=ticket_id, **payload.model_dump())
    ticket.status = "PAUSED"
    db.commit()
    create_new_pause(db, data, current_user)
    return ticket