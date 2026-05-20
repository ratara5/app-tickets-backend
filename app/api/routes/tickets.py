from fastapi import APIRouter, Depends

from app.api.routes import get_current_user
from app.core.database import get_db
from app.services.ticket_service import create_new_ticket, list_tickets
from app.schemas.ticket import TicketCreate

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