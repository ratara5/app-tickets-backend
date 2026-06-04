import datetime

from sqlalchemy import or_, and_, joinedload, select
from sqlalchemy.orm import Session

from app.core.utils.dates import start_of_month

from app.models.ticket import Ticket, AddWkd
from app.models.master import Technician

from app.schemas.ticket import TicketStatus
from app.schemas.user import UserRole


def save_ticket(db, data, current_user):
    ticket = Ticket(
        ticket_id=data.ticket_id,
        ticket_date=data.ticket_date or datetime.now().strftime("%d/%m/%Y"), # TODO: To inject TZ from environment and apply .strftime("%d/%m/%Y") 
        ticket_description=data.ticket_description,
        priority=data.priority,
        status=TicketStatus.open, # "OPEN"
        market_id=data.market_id,
        equipment_id=data.equipment_id
        # created_by=current_user.user_id # It's not necessary overwrite auditmixin
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return ticket

def get_visible_tickets(db, current_user, page: int = 1, page_size: int = 50):
    query = _get_query(db, current_user, None)

    return query.order_by(
        Ticket.ticket_date.desc()
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    ).all()

def get_ticket_by_id( # The client side cache eliminates 90% calls to this endpoint.
    db: Session, 
    ticket_id: int, 
    current_user
) -> Ticket | None:
    query = _get_query(db, current_user, ticket_id)
    query = query.filter(Ticket.ticket_id == ticket_id)
    
    return query.first()

def _get_query(db, current_user):
    limit_date = start_of_month(-2)
    query = (
    db.query(Ticket)
    .options(
        joinedload(Ticket.market),
        joinedload(Ticket.equipment),
        # joinedload(Ticket.cancellation),
        joinedload(Ticket.technician)
            .joinedload(Technician.fsm_user)
        )
        .filter(Ticket.ticket_date >= limit_date)
    )

    if current_user.user_role == UserRole.technician:
        query = query.filter(
            and_(
                or_(
                    Ticket.assigned_to == None,
                    Ticket.assigned_to == current_user.technician.technician_id
                ),
                Ticket.status != TicketStatus.cancelled # "CANCELLED"
            )
        )
    
    return query

def save_add_wkd(db, data, current_user):
    add_wkd = AddWkd(
        ticket_id=data.ticket_id,
        operation_percentage=data.operation_percentage,
        market_temperature=data.temperature,
        operation_damage=data.operatin_damage,
        completed=data.completed,
        observations_wkd=data.observations_wkd
    )

    db.add(add_wkd)
    db.commit()
    db.refresh(add_wkd)

    return add_wkd

def delete_ticket_by_id(db, ticket, current_user):

    db.delete(ticket)
    db.commit()
   
    return ticket.ticket_id
    
