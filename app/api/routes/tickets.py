from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes import get_current_user
from app.core.database import get_db
from app.services.ticket_service import (create_new_ticket, 
                                         list_tickets, 
                                         assign_ticket, 
                                         start_mantenimiento,
                                         cancel_ticket,
                                         pause_ticket)

from app.schemas.ticket import TicketCreate, AssignRequest
from app.schemas.cancelacion import CancelacionRequest
from app.schemas.pausa import PausaRequest

router = APIRouter(prefix="/tickets")

@router.get("")
def get_tickets(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):

    return list_tickets(db, current_user, page, page_size)

@router.post("")
def create_ticket(
    data: TicketCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):

    return create_new_ticket(
        db,
        data,
        current_user
    )

@router.patch("/{ticket_id}/assign")
def assign(nro_ticket: int, 
           payload: AssignRequest,
           db: Session = Depends(get_db),
           current_user = Depends(get_current_user)):
    # Admin puede asignarse a sí mismo o a cualquier técnico, técnico solo a sí mismo
    # ...
    return assign_ticket(nro_ticket, payload, current_user, db)

@router.patch("/{ticket_id}/start")
def start(nro_ticket: int, 
          current_user = Depends(get_current_user),
          db: Session = Depends(get_db)):
    return start_mantenimiento(nro_ticket, current_user, db)

@router.patch("/{ticket_id}/cancel")
def cancel(ticket_id: int, payload: CancelacionRequest,
           db: Session = Depends(get_db),
           current_user = Depends(get_current_user)):
    return cancel_ticket(ticket_id, payload, current_user, db)

@router.patch("/{ticket_id}/pause")
def pause(ticket_id: int, payload: PausaRequest,
          db: Session = Depends(get_db),
          current_user = Depends(get_current_user)):
    return pause_ticket(ticket_id, payload, current_user, db)