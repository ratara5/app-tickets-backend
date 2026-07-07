from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db

from app.schemas.ticket import TicketCreate, AssignRequest, TicketItemResponse, AddWkdRequest
from app.schemas.maintenance import MaintenanceCreate
from app.schemas.cancellation import CancellationRequest

from app.services.ticket_service import *


router = APIRouter(prefix="/tickets")

@router.get("", response_model=list[TicketItemResponse])
def get_tickets(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return list_tickets(db, current_user, page, page_size)

@router.get("/{ticket_id}", response_model=TicketItemResponse)
def get_ticket_by_id_route(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TicketItemResponse:
    return get_ticket(db, ticket_id, current_user)

@router.post("", response_model=TicketItemResponse, status_code=201)
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

@router.patch("/{ticket_id}/assign", response_model=TicketItemResponse)
def assign(ticket_id: int, 
           payload: AssignRequest,
           db: Session = Depends(get_db),
           current_user = Depends(get_current_user)):
    # Admin can assign tk to himself or at any technician, technician only assign tk to himself
    # ...
    return assign_ticket(ticket_id, payload, current_user, db)

@router.patch("/{ticket_id}/start", response_model=MaintenanceCreate)
def start_maintenance_route(ticket_id: int, 
          current_user = Depends(get_current_user),
          db: Session = Depends(get_db)):
    return start_maintenance(ticket_id, None, current_user, db)
 
@router.patch("/{ticket_id}/cancel", response_model=TicketItemResponse)
def cancel(ticket_id: int, payload: CancellationRequest,
           db: Session = Depends(get_db),
           current_user = Depends(get_current_user)):
    return cancel_ticket(ticket_id, payload, current_user, db)

# @router.patch("/{ticket_id}/pause")
# Now in routes/maintenances.py because it's more related to maintenance than ticket, and it needs to validate the maintenance status and not the ticket status. The endpoint is /maintenances/{maintenance_id}/pause instead of /tickets/{ticket_id}/pause because the pause is more related to the maintenance than the ticket, and we need to validate the maintenance status before pausing it. The ticket status is automatically updated to paused when the maintenance is paused, so we don't need to validate the ticket status.

@router.patch("/{ticket_id}/addwkd", response_model=TicketItemResponse)
def create_add_wkd(ticket_id: int, payload: AddWkdRequest,
          db: Session = Depends(get_db),
          current_user = Depends(get_current_user)):
    return create_new_add_wkd (ticket_id, payload, current_user, db)

@router.delete("/{ticket_id}", status_code=204)
def del_ticket(ticket_id: int, 
               db: Session = Depends(get_db), 
               current_user = Depends(get_current_user)):
    return delete_ticket(ticket_id, current_user, db)