import datetime

from sqlalchemy import or_, and_
from app.models.mantenimiento import Mantenimiento
from app.models.ticket import Ticket
from app.core.utils.dates import start_of_month

def create_mantenimiento(db, nro_ticket, current_user):

    mantenimiento = Mantenimiento(
        nro_ticket=nro_ticket,
        fecha_trabajo=datetime.date.today(),
        created_by=current_user.email
    )

    db.add(mantenimiento)
    db.flush()
    db.refresh(mantenimiento)

    return mantenimiento

def get_visible_mantenimientos(db, current_user, page: int = 1, page_size: int = 50):

    fecha_limite = start_of_month(-2)

    query = (
        db.query(Mantenimiento)
        .join(Mantenimiento.ticket)
        .filter(
            Ticket.fecha_ticket >= fecha_limite
        )
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