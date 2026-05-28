import datetime

from sqlalchemy import or_, and_
from app.core.utils.dates import start_of_month

from app.models.ticket import Ticket
from app.models.maintenance import Mantenimiento, MantenimientoRepuesto, MantenimientoTecnico

def create_mantenimiento(db, data, current_user):

    mantenimiento = Mantenimiento(
        nro_ticket=data.nro_ticket,
        fecha_trabajo=data.fecha_trabajo or datetime.now().strftime("%d/%m/%Y"), # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad")).strftime("%d/%m/%Y")
        created_by=current_user.email
    )

    db.add(mantenimiento)
    db.flush()
    db.refresh(mantenimiento)

    return mantenimiento

def save_mantenimiento(db, data, current_user):
    mantenimiento = Mantenimiento(
        nro_ticket=data.nro_ticket,
        descripcion_trabajo=data.descripcion_trabajo,
        inicio_mantenimiento=data.inicio_mantenimiento, # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad"))
        archivo_foto_inicio=data.archivo_foto_inicio,
        tipo_jornada=data.tipo_jornada,

        carpeta_soporte=data.carpeta_soporte,
        formato_soporte=data.formato_soporte,
        url_foto_inicio=data.url_foto_inicio,
        url_informe_soporte=data.url_informe_soporte,

        created_by=current_user.email
    )
    db.add(mantenimiento)
    db.flush()  # obtener el ID sin hacer commit

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

def add_mantenimiento_repuesto(db, id_mantenimiento, r):
    db.add(MantenimientoRepuesto(
        id_mantenimiento=id_mantenimiento,
        id_repuesto=r.id_repuesto,
        cantidad=r.cantidad
    ))
def add_mantenimiento_tecnico(db, id_mantenimiento, t):
    db.add(MantenimientoTecnico(
        id_mantenimiento_id=id_mantenimiento,
        id_tecnico=t.id_tecnico,
        hora_entrada=t.hora_entrada,
        hora_salida=t.hora_salida
    ))