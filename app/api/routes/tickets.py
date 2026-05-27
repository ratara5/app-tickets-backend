from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.services.ticket_service import (create_new_ticket, 
                                         list_tickets, 
                                         assign_ticket, 
                                         start_maintenance,
                                         cancel_ticket,
                                         pause_ticket)

from app.schemas.ticket import TicketCreate, AssignRequest
from app.schemas.cancellation import CancellationRequest
from app.schemas.pause import PauseRequest

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
def assign(ticket_id: int, 
           payload: AssignRequest,
           db: Session = Depends(get_db),
           current_user = Depends(get_current_user)):
    # Admin can assign tk to himself or at any technician, technician only assign tk to himself
    # ...
    return assign_ticket(ticket_id, payload, current_user, db)

@router.patch("/{ticket_id}/start")
def start(ticket_id: int, 
          current_user = Depends(get_current_user),
          db: Session = Depends(get_db)):
    return start_maintenance(ticket_id, current_user, db)

@router.patch("/{ticket_id}/cancel")
def cancel(ticket_id: int, payload: CancellationRequest,
           db: Session = Depends(get_db),
           current_user = Depends(get_current_user)):
    return cancel_ticket(ticket_id, payload, current_user, db)

@router.patch("/{ticket_id}/pause")
def pause(ticket_id: int, payload: PauseRequest,
          db: Session = Depends(get_db),
          current_user = Depends(get_current_user)):
    return pause_ticket(ticket_id, payload, current_user, db)