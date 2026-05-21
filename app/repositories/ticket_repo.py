import datetime

from sqlalchemy import or_, and_
from app.models.ticket import Ticket
from app.core.utils.dates import start_of_month

from app.models.ticket import Ticket

def save_ticket(db, data, current_user):

    ticket = Ticket(
        prioridad="MEDIA",
        fecha_ticket=data.fecha_ticket,
        descripcion_ticket=data.descripcion_ticket,
        estado="ABIERTO",
        created_by=current_user.email
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return ticket

def get_visible_tickets(db, current_user, page: int = 1, page_size: int = 50):

    fecha_limite = start_of_month(-2)

    query = db.query(Ticket).filter(
        Ticket.fecha_ticket >= fecha_limite
    )

    if current_user.role == "TECNICO":

        query = query.filter(
            and_(
                or_(
                    Ticket.asignado_a == None,
                    Ticket.asignado_a == current_user.tecnico.id_tecnico
                ),
                Ticket.estado != "CANCELADO"
            )
        )

    return query.order_by(
        Ticket.fecha_ticket.desc()
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    ).all()