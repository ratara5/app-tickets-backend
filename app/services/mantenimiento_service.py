from types import SimpleNamespace
from pydantic import UUID7

from datetime import datetime
import secrets, asyncio, io

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

from app.services.registry import service

from app.core.storage import upload_file, get_presigned_url
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor()  # para operaciones síncronas de MinIO

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png", 
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "image/svg+xml": ".svg",
}

def create_new_mantenimiento(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...

    mantenimiento = create_mantenimiento(db, data, current_user)
    
    # Lógica de negocio después de persistir
    # ...

    return mantenimiento

async def update_existing(id_mantenimiento: UUID7, payload: MantenimientoUpdate, current_user, db: Session, files: dict):
    # Obtener el mantenimiento
    mantenimiento = db.query(Mantenimiento).filter(Mantenimiento.id == id_mantenimiento).first()
    # Verificar que el ticket asociado existe y está EN_PROGRESO o PAUSADO
    ticket = db.query(Ticket).filter(Ticket.nro_ticket == mantenimiento.nro_ticket).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    if ticket.estado not in ("EN_PROGRESO", "PAUSADO"):
        raise HTTPException(
            422, f"No se puede crear mantenimiento: ticket en estado {ticket.estado}"
        )
    
    
    # Lógica de negocio antes de persistir
    ## Subir los archivos del mantenimiento
    col_val_info = dict[str, str]
    for col_name, upload_file_obj in files.items():
        if upload_file_obj is None:
            continue
        content = await upload_file_obj.read()
        _, original_filename, full_object_path = build_object_path_mantenimientos(
            mantenimiento, col_name, upload_file_obj.content_type
        )
        result = await asyncio.get_event_loop().run_in_executor(
            _executor,
            lambda: upload_file(
                file_stream=io.BytesIO(content),
                original_filename=original_filename,
                content_type=upload_file_obj.content_type,
                full_object_path=full_object_path,
                job_id=str(id_mantenimiento),
            )
        )
        url_col = "_".join(col_name.split("_")[1:])
        url = get_presigned_url(full_object_path, 1)
        col_val_info[col_name] = full_object_path
        col_val_info[url_col] = url
        # setattr(mantenimiento, col_name, full_object_path) # result["url_path"] es interna, del tipo /bucket/objeto
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
                           real_marcar_como=real_marcar_como,
                           **col_val_info
                           )

    # Guardar cambios en mantenimiento (persistir)
    mantenimiento = save_mantenimiento(db, data, current_user)

    # Lógica de negocio después de persistir
    ## Persistir repuestos, técnicos, fotos, etc. relacionados a ese mantenimiento
    ### Repuestos
    for r in payload.repuestos:
        add_mantenimiento_repuesto(db, mantenimiento.id, r)
    ### Técnicos
    for t in payload.tecnicos:
        add_mantenimiento_tecnico(db, mantenimiento.id, t)
    return mantenimiento

def list_mantenimientos(db, current_user, page: int = 1, page_size: int = 50):
    return get_visible_mantenimientos(db, current_user, page, page_size)



@service(schema=Mantenimiento)
def build_object_path_mantenimientos(mantenimiento: Mantenimiento, col_name, content_type):

    fecha_trabajo = mantenimiento.fecha_trabajo
    mes = fecha_trabajo.strftime("%B")
    anio = fecha_trabajo.strftime("%Y")
    serial = secrets.token_hex(4)
    ext = EXT_BY_TYPE.get(content_type, "")

    original_filename = f"{mantenimiento.id}.{col_name}.{serial}.{ext}"
    full_object_path = f"Mantenimiento/Correctivos/{anio}/{mes}/{mantenimiento.nro_ticket}/{original_filename}"
    
    return serial, original_filename, full_object_path