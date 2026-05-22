from datetime import datetime
from types import SimpleNamespace

from app.core.utils.dates import CO_HOLIDAYS
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.ticket import Ticket
from app.models.mantenimiento import Mantenimiento
from app.models.pausa import Pausa

from app.schemas.mantenimiento import MantenimientoCreate, MantenimientoUpdate

from app.repositories.mantenimiento_repo import (create_mantenimiento, 
                                                save_mantenimiento, 
                                                get_visible_mantenimientos,
                                                add_mantenimiento_repuesto,
                                                add_mantenimiento_tecnico)

def create_new_mantenimiento(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...

    mantenimiento = create_mantenimiento(db, data, current_user)
    
    # Lógica de negocio después de persistir
    # ...

    return mantenimiento

def update_existing(nro_ticket: int, payload: MantenimientoUpdate, current_user, db: Session):
    # Verificar que el ticket existe y está EN_PROGRESO o PAUSADO
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == payload.nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    if ticket.estado not in ("EN_PROGRESO", "PAUSADO"):
        raise HTTPException(
            422, f"No se puede crear mantenimiento: ticket en estado {ticket.estado}"
        )
    # Obtener el mantenimiento asociado a ese ticket
    mantenimiento = db.query(Mantenimiento).filter(Mantenimiento.nro_ticket == payload.nro_ticket).first()
    
    # Lógica de negocio antes de persistir
    ## Obtener valores de campos calculados o derivados
    ### inicio_mantenimiento
    inicio_mantenimiento = mantenimiento.inicio_mantenimiento or datetime.now().strftime("%Y-%m-%d %H:%M:%S+00") # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad"))
    ### inicio_edicion calculado ahora si es que no está en mantenimiento
    inicio_edicion = mantenimiento.inicio_edicion or datetime.now().strftime("%Y-%m-%d %H:%M:%S+00") # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad"))
    ### tipo_jornada según fecha_ticket
    tipo_jornada = 1
    fecha_ticket = ticket.fecha_ticket
    if fecha_ticket.weekday() >= 5 or fecha_ticket in CO_HOLIDAYS:
        tipo_jornada = 3 # Feriado
    ### real_marcar_como 
    #- Obtener el id_mantenimiento
    id_mantenimiento = mantenimiento.id_mantenimiento
    #- Obtener las pausas (si existen) asociadas a ese id_mantenimiento
    pausas = db.query(Pausa).filter(
        Pausa.id_mantenimiento == id_mantenimiento
    ).order_by(Pausa.fecha_hora_pausa.desc()).first()
    #- Obtener la pausa más reciente (fecha_hora_pausa mayor)
    ultima_pausa = max(pausas, key=lambda p: p.fecha_hora_pausa)
    #- Comparar inicio_edicion con fecha_hora_pausa mayor
    #-- Si inicio_edicion < fecha_hora_pausa mayor → real_marcar_como = "PAUSADO"
    if inicio_edicion < ultima_pausa.fecha_hora_pausa:
        real_marcar_como = "PAUSADO"
    #-- Si inicio_edicion > fecha_hora_pausa mayor → real_marcar_como = "EJECUTADO"
    else:
        real_marcar_como = "EJECUTADO"

    data = SimpleNamespace(**payload.model_dump(), 
                           inicio_mantenimiento=inicio_mantenimiento, 
                           inicio_edicion=inicio_edicion,
                           tipo_jornada=tipo_jornada,
                           real_marcar_como=real_marcar_como)

    # Guardar cambios en mantenimiento (persistir)
    mantenimiento = save_mantenimiento(db, data, current_user)

    # Lógica de negocio después de persistir
    ## Persistir repuestos, técnicos, fotos, etc. relacionados a ese mantenimiento
    ### Repuestos
    for r in payload.repuestos:
        add_mantenimiento_repuesto(db, mantenimiento.id, r)
    ### Técnicos
    for t in payload.tecnicos_adicionales:
        add_mantenimiento_tecnico(db, mantenimiento.id, t)
    return mantenimiento
    ### Fotos
    # Previamente, implementar lógica de upload de fotos a S3 y obtener URLs para guardar en mantenimiento.url_foto_inicio, mantenimiento.url_informe_soporte, y todas las url_archivo_foto

def list_mantenimientos(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_mantenimientos(db, current_user, page, page_size)