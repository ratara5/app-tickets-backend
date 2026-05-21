import datetime

from sqlalchemy import or_, and_
from app.models.ticket import Ticket
from app.core.utils.dates import start_of_month

from app.models.cancelacion import Cancelacion

def save_cancelacion(db, data, current_user):

    cancelacion = Cancelacion(
        nro_ticket=data.nro_ticket,
        fecha_cancelacion=datetime.datetime.today().strftime("%d/%m/%Y"),
        motivo_cancelacion=data.motivo_cancelacion,
        responsable_cancelacion=current_user.email,
        created_by=current_user.email
    )

    db.add(cancelacion)
    db.commit()
    db.refresh(cancelacion)

    return cancelacion

def get_cancelaciones(db, current_user, page: int = 1, page_size: int = 50):
    pass