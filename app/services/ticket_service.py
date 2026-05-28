from datetime import date
from types import SimpleNamespace

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.repositories.ticket_repo import save_ticket, get_visible_tickets

from app.models.ticket import Ticket
from app.models.tecnico import Tecnico

from app.schemas.ticket import AssignRequest
from app.schemas.cancellation import CancelacionRequest
from app.schemas.pause import PausaRequest

from app.services.mantenimiento_service import create_new_mantenimiento
from app.services.cancelacion_service import create_new_cancelacion
from app.services.pausa_service import create_new_pausa

def create_new_ticket(db, data, current_user):
    return save_ticket(db, data, current_user)

def list_tickets(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_tickets(db, current_user, page, page_size)

VALID_TRANSITIONS = {
    "ABIERTO": ["ASIGNADO", "CANCELADO"],
    "ASIGNADO": ["EN PROGRESO", "CANCELADO"],
    "EN PROGRESO": ["PAUSADO", "EJECUTADO", "CANCELADO"],
    "PAUSADO": ["EN PROGRESO", "CANCELADO"],
    "CANCELADO": [],
    "EJECUTADO": []
}

def _validate_transition(current_state: str, new_state: str):
    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {current_state} → {new_state}"
        )
    
# ── a. Iniciar mantenimiento (EN_PROGRESO) ────────────────────────────────────
def start_mantenimiento(nro_ticket: int, payload: None,
                 current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    
    
    _validate_transition(ticket.estado, "EN_PROGRESO")
    
    # Validación festivos/fin de semana: No necesaria
    # ...

    data = SimpleNamespace(nro_ticket=nro_ticket, **payload.model_dump() if payload else {})
    ticket.estado = "EN_PROGRESO"
    db.commit()
    create_new_mantenimiento(db, data, current_user)
    return ticket

# ── b. Asignar técnico ────────────────────────────────────────────────────────
def _get_tecnico_id_by_user(db, current_user):
    tecnico = db.query(Tecnico).filter(
        Tecnico.email == current_user.email
    ).first()
    if not tecnico:
        raise HTTPException(404, "Tu usuario no tiene técnico asociado")
    return tecnico.id_tecnico if tecnico else None

def assign_ticket(nro_ticket: int, payload: AssignRequest,
                  current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    
    _validate_transition(ticket.estado, "ASIGNADO")

    if current_user.rol not in ["TECNICO", "DIRECTOR"]:
        raise HTTPException(400, "No puede asignar")
    
    tecnico_id = _get_tecnico_id_by_user(db, current_user)

    if payload.tecnico_id and current_user.rol == "DIRECTOR":
        tecnico_id = payload.tecnico_id

    ticket.estado = "ASIGNADO"
    ticket.asignado_a = tecnico_id
    db.commit()
    return ticket

# ── c. Cancelar ───────────────────────────────────────────────────────────────
def cancel_ticket(nro_ticket: int, payload: CancelacionRequest,
                  current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    
    _validate_transition(ticket.estado, "CANCELADO")

    data = SimpleNamespace(nro_ticket=nro_ticket, **payload.model_dump())
    ticket.estado = "CANCELADO"
    db.commit()
    create_new_cancelacion(db, data, current_user)
    return ticket
    
# ── c. Pausar ───────────────────────────────────────────────────────────────
def pause_ticket(nro_ticket: int, payload: PausaRequest,
                  current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    
    _validate_transition(ticket.estado, "PAUSADO")

    data = SimpleNamespace(nro_ticket=nro_ticket, **payload.model_dump())
    ticket.estado = "PAUSADO"
    db.commit()
    create_new_pausa(db, data, current_user)
    return ticket