from datetime import datetime
from uuid6 import uuid7
import os, aiofiles, asyncio, hashlib, secrets

from sqlalchemy.orm import Session
from fastapi import HTTPException

from concurrent.futures import ThreadPoolExecutor
from app.core.storage import upload_file, get_presigned_url

from app.repositories.upload_repo import (get_upload_session, 
                                          save_upload_session, 
                                          get_chunks_on_disk,
                                          get_chunks_missing,
                                          assemble_chunks,
                                          clean_chunks,
                                          mark_completed)

from app.models.ticket import Ticket
from app.models.mantenimiento import Mantenimiento
from app.models.upload import UploadSession

from app.schemas.ticket import AssignRequest
from app.schemas.cancelacion import CancelacionRequest
from app.schemas.pausa import PausaRequest
from app.schemas.upload import UploadInitRequest, UploadInitResponse, ChunkResponse
from app.schemas.file import FileSave

from app.services.mantenimiento_service import create_new_mantenimiento

from app.services.registry import _autodiscover, dispatch_service, dispatch_build_path
from app.models.registry import _autodiscover_models, get_model

from app.core import settings

chunk_dir = settings.chunk_dir
os.makedirs(chunk_dir, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", 
                        "application/pdf", "image/svg+xml"}

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png", 
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "image/svg+xml": ".svg",
}

async def init_upload_service(db: Session, current_user, payload):
    # Aquí iría la lógica para crear una nueva sesión de carga 
    # 1. Validar el payload (tipo de archivo permitido, tamaño máximo, etc.)
    if payload.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Tipo no permitido: {payload.content_type}")
    
    # 2.
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    if payload.total_size > MAX_SIZE:
        raise HTTPException(413, "Archivo demasiado grande (máx 50 MB)")

    upload_id = str(uuid7())

    # Persistir
    upload_session = save_upload_session(db, upload_id, current_user.email, payload) # Sesion es síncrona, no async, por eso no await

    return UploadInitResponse(
        upload_id=upload_id,
        chunk_size=1 * 1024 * 1024,  # 1 MB
        next_chunk=0,
    )


async def upload_chunk_service(db: Session, current_user, upload_id, chunk_index, chunk, x_chunk_checksum):
    upload_session = get_upload_session(db, upload_id, current_user.email) # Sesion es síncrona, no async, por eso no await
    if not upload_session:
        raise HTTPException(404, "Sesión de upload no encontrada")
    if upload_session.expires_at < datetime.now():
        raise HTTPException(410, "Sesión expirada. Inicia un nuevo upload.")
    if chunk_index >= upload_session.total_chunks:
        raise HTTPException(422, "chunk_index fuera de rango")

    chunk_data = await chunk.read()

    # Verificar checksum si el cliente lo envió
    if x_chunk_checksum:
        md5 = hashlib.md5(chunk_data).hexdigest()
        if md5 != x_chunk_checksum:
            raise HTTPException(422, "Checksum incorrecto — reenvía el chunk")

    # Guardar chunk en disco temporal
    chunk_path = os.path.join(chunk_dir, f"{upload_id}_{chunk_index:04d}")
    async with aiofiles.open(chunk_path, "wb") as f:
        await f.write(chunk_data)

    # Actualizar contador (idempotente: si el chunk ya existía, no suma de nuevo)
    chunks_in_disk = get_chunks_on_disk(upload_id)

    ## Persistir: inútil una función en repo para esto
    upload_session.received_chunks = chunks_in_disk
    db.commit() # Session es síncrona, no async, por eso no await

    return ChunkResponse(
        upload_id=upload_id,
        chunk_index=chunk_index,
        received_chunks=upload_session.received_chunks,
        total_chunks=upload_session.total_chunks
    )


_executor = ThreadPoolExecutor()  # para operaciones síncronas de MinIO
_autodiscover("app.services")
_autodiscover_models("app.models")
async def complete_upload_service(db: Session, upload_id: str, current_user):
    # 1. Validar sesión
    upload_session = get_upload_session(db, upload_id, current_user.email)
    if not upload_session:
        raise HTTPException(404, "Sesión no encontrada")
    if upload_session.completado:
        raise HTTPException(409, "Upload ya completado")

    # 2. Verificar chunks
    chunks_faltantes = get_chunks_missing(upload_id, upload_session.total_chunks)
    if chunks_faltantes:
        raise HTTPException(422, detail={
            "error": "CHUNKS_INCOMPLETOS",
            "recibidos": upload_session.total_chunks - len(chunks_faltantes),
            "esperados": upload_session .total_chunks,
            "chunks_faltantes": chunks_faltantes,
        })

    # 3. Ensamblar en disco (no en memoria)
    chunks_en_disco = get_chunks_on_disk(upload_id)
    assembled_path = await assemble_chunks(upload_id, chunks_en_disco)
    size_bytes = os.path.getsize(assembled_path)

    # 4. Subir a MinIO en thread (cliente boto3 es síncrono)
    #- Atributos minio (bucket (más sencillo), original_filename...) según el: parent_id, modelo relacionado de parent_tab, col_name
    parent_id = upload_session.parent_id
    parent_tab = upload_session.parent_tab
    
    ParentModel = get_model(parent_tab)
    parent = db.query(ParentModel).filter( 
        ParentModel.id == parent_id
        ).first()
    
    # ANTES #
    # fecha_trabajo = mantenimiento.fecha_trabajo
    # mes = fecha_trabajo.strftime("%B")
    # anio = fecha_trabajo.strftime("%Y")
    # original_filename = f"{upload_session.entity_id}.{upload_session.col_name}.{serial}{ext}"
    # full_object_path = f"Mantenimiento/Correctivos/{anio}/{mes}/{mantenimiento.nro_ticket}/{original_filename}" #... ruta sencilla basada en anio y mes actuales y en entity_parent
    #########
    serial, original_filename, full_object_path = await dispatch_build_path(parent, 
                                                                    upload_session.col_name, 
                                                                    upload_session.content_type)


    # - Subir a MinIO
    with open(assembled_path, "rb") as file_stream:
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                _executor,
                lambda: upload_file(
                    file_stream=file_stream, 
                    original_filename=original_filename,
                    content_type=upload_session.content_type,
                    full_object_path=full_object_path,
                    job_id=upload_id
                )
            )
        except Exception as e:
            raise HTTPException(502, f"Error subiendo a MinIO: {str(e)}")
    # - URL
    url = get_presigned_url(full_object_path, 1)
        

    # 5. Persistir registro con info del archivo subido BD 
    # - Definir el repo según la tabla o según la ext (lo mismo?)
    tab_name = upload_session.tab_name
    # - La entidad para el registro genérico se construye acá y se hace particular en el repo llamado desde el service
    file = FileSave(
        id_file=serial,
        id_parent=parent_id,
        archivo_file=full_object_path,
        url_file=url
    )

    result = dispatch_service(tab_name, db, file, current_user)

    # - Marcar upload como efectivamente completada
    mark_completed(db, upload_session)  # commit aquí

    # 6. Limpiar chunks — después del commit
    clean_chunks(upload_id, chunks_en_disco, assembled_path)

    