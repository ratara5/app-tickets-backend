from datetime import datetime
from uuid6 import uuid7
import os, aiofiles, hashlib

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.repositories.upload_repo import save_upload_session

from app.models.ticket import Ticket
from app.models.tecnico import Tecnico
from app.models.upload import UploadSession

from app.schemas.ticket import AssignRequest
from app.schemas.cancelacion import CancelacionRequest
from app.schemas.pausa import PausaRequest
from app.schemas.upload import UploadInitRequest, UploadInitResponse, ChunkResponse

from app.services.mantenimiento_service import create_new_mantenimiento

CHUNK_DIR = "/tmp/upload_chunks"
os.makedirs(CHUNK_DIR, exist_ok=True)

async def init_upload_service(db: Session, current_user, payload):
    # Aquí iría la lógica para crear una nueva sesión de carga 
    # 1. Validar el payload (tipo de archivo permitido, tamaño máximo, etc.)
    ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", 
                        "application/pdf", "image/svg+xml"}
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
    upload_session = db.query(UploadSession).filter(
        UploadSession.id == upload_id,
        UploadSession.usuario_id == current_user.id,
    ).first()
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
    chunk_path = os.path.join(CHUNK_DIR, f"{upload_id}_{chunk_index:04d}")
    async with aiofiles.open(chunk_path, "wb") as f:
        await f.write(chunk_data)

    # Actualizar contador (idempotente: si el chunk ya existía, no suma de nuevo)
    chunks_in_disk = len([
        f for f in os.listdir(CHUNK_DIR) 
        if f.startswith(upload_id + "_")
    ])

    ## Persistir: inútil una función en repo para esto
    upload_session.received_chunks = chunks_in_disk
    db.commit() # Session es síncrona, no async, por eso no await

    return ChunkResponse(
        upload_id=upload_id,
        chunk_index=chunk_index,
        received_chunks=upload_session.received_chunks,
        total_chunks=upload_session.total_chunks
    )
