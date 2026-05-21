from datetime import date
import holidays
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.repositories.tickets import save_ticket
from app.repositories.tickets import get_visible_tickets
from app.repositories.mantenimientos import create_mantenimiento

from app.models.ticket import Ticket
from app.models.tecnico import Tecnico
from app.schemas.ticket import AssignRequest

def create_new_ticket(db, data, current_user):
    return save_ticket(db, data, current_user)

def list_tickets(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_tickets(db, current_user, page, page_size)

CO_HOLIDAYS = holidays.Colombia() # TODO: Inyectar TZ y país como variables de entorno

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
def start_mantenimiento(nro_ticket: int,
                 current_user, db: Session):
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    
    
    _validate_transition(ticket.estado, "EN_PROGRESO")
    
    # Validación festivos/fin de semana: No necesaria
    # ...

    ticket.estado = "EN_PROGRESO"
    db.commit()
    create_mantenimiento(db, nro_ticket, current_user)
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


