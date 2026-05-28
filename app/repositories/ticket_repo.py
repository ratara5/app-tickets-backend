import datetime

from sqlalchemy import or_, and_

from app.core.utils.dates import start_of_month

from app.models.ticket import Ticket


def save_ticket(db, data, current_user):

    ticket = Ticket(
        priority="MEDIUM",
        ticket_date=data.ticket_date or datetime.now().strftime("%d/%m/%Y"), # TODO: To inject TZ from environment and apply .strftime("%d/%m/%Y") 
        ticket_description=data.ticket_description,
        status="OPEN",
        # created_by=current_user.user_id # It's not necessary overwrite auditmixin
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return ticket

def get_visible_tickets(db, current_user, page: int = 1, page_size: int = 50):
    limit_date = start_of_month(-2)

    query = db.query(Ticket).filter(
        Ticket.ticket_date >= limit_date
    )

    if current_user.user_role == "TECHNICIAN":
        query = query.filter(
            and_(
                or_(
                    Ticket.assigned_to == None,
                    Ticket.assigned_to == current_user.technician.technician_id
                ),
                Ticket.status != "CANCELLED"
            )
        )

    return query.order_by(
        Ticket.ticket_date.desc()
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    ).all()