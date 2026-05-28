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
from app.models.maintenance import Maintenance
from app.models.upload import UploadSession

from app.schemas.ticket import AssignRequest
from app.schemas.cancellation import CancelacionRequest
from app.schemas.pause import PausaRequest
from app.schemas.upload import UploadInitRequest, UploadInitResponse, ChunkResponse
from app.schemas.file import FileSave

from app.services.maintenance_service import create_new_maintenance

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
    # Here the logic in order to create new upload session 
    # 1. Validates payload (allow file type, max size, etc.)
    if payload.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Type not allowed: {payload.content_type}")
    
    # 2.
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    if payload.total_size > MAX_SIZE:
        raise HTTPException(413, "File too large (max 50 MB)")

    upload_id = str(uuid7())

    # Persists
    upload_session = save_upload_session(db, upload_id, current_user.email, payload) # Session is sync, not async, therefore no await

    return UploadInitResponse(
        upload_id=upload_id,
        chunk_size=1 * 1024 * 1024,  # 1 MB
        next_chunk=0,
    )

async def upload_chunk_service(db: Session, current_user, upload_id, chunk_index, chunk, x_chunk_checksum):
    upload_session = get_upload_session(db, upload_id, current_user.email) # Session is sync, not async, therefore no await
    if not upload_session:
        raise HTTPException(404, "Upload sesion not found")
    if upload_session.expires_at < datetime.now():
        raise HTTPException(410, "Expired sesion. Please start a new upload.")
    if chunk_index >= upload_session.total_chunks:
        raise HTTPException(422, "Chunk index out of range")

    chunk_data = await chunk.read()

    # Verify checksum if client send it
    if x_chunk_checksum:
        md5 = hashlib.md5(chunk_data).hexdigest()
        if md5 != x_chunk_checksum:
            raise HTTPException(422, "Incorrect checksum — please resend the chunk")

    # Save chunk in temporary disk
    chunk_path = os.path.join(chunk_dir, f"{upload_id}_{chunk_index:04d}")
    async with aiofiles.open(chunk_path, "wb") as f:
        await f.write(chunk_data)

    # Update counter (idempotent: if the chunk already existed, it is not added again)
    chunks_in_disk = get_chunks_on_disk(upload_id)

    ## Persist: It's useless to add a function
    upload_session.received_chunks = chunks_in_disk
    db.commit() # Session is sync, no async, therefore no await

    return ChunkResponse(
        upload_id=upload_id,
        chunk_index=chunk_index,
        received_chunks=upload_session.received_chunks,
        total_chunks=upload_session.total_chunks
    )

_executor = ThreadPoolExecutor()  # for synchronous operations in Minio
_autodiscover("app.services")
_autodiscover_models("app.models")
async def complete_upload_service(db: Session, upload_id: str, current_user):
    # 1. Validate session
    upload_session = get_upload_session(db, upload_id, current_user.email)
    if not upload_session:
        raise HTTPException(404, "Session not found")
    if upload_session.completed:
        raise HTTPException(409, "Upload is already completed")

    # 2. Verify chunks
    missing_chunks = get_chunks_missing(upload_id, upload_session.total_chunks)
    if missing_chunks:
        raise HTTPException(422, detail={
            "error": "INCOMPLETED_CHUNKS",
            "received": upload_session.total_chunks - len(missing_chunks),
            "expected": upload_session .total_chunks,
            "missing_chunks": missing_chunks,
        })

    # 3. Assemble in disk (not in memory)
    chunks_in_disk = get_chunks_on_disk(upload_id)
    assembled_path = await assemble_chunks(upload_id, chunks_in_disk)
    size_bytes = os.path.getsize(assembled_path)

    # 4. Upload to MinIO in thread (boto3 client is synchronous)
    #- Minio attributes (bucket (more simply), original_filename...) according: parent_id, related model of parent_tab, col_name
    parent_id = upload_session.parent_id
    parent_tab = upload_session.parent_tab
    
    ParentModel = get_model(parent_tab)
    parent = db.query(ParentModel).filter( 
        ParentModel.id == parent_id
        ).first()
    
    # ANTES #
    # fecha_trabajo = maintenance.fecha_trabajo
    # mes = fecha_trabajo.strftime("%B")
    # anio = fecha_trabajo.strftime("%Y")
    # original_filename = f"{upload_session.entity_id}.{upload_session.col_name}.{serial}{ext}"
    # full_object_path = f"Mantenimiento/Correctivos/{anio}/{mes}/{mantenimiento.nro_ticket}/{original_filename}" #... ruta sencilla basada en anio y mes actuales y en entity_parent
    #########
    serial, original_filename, full_object_path = await dispatch_build_path(parent, 
                                                                    upload_session.col_name, 
                                                                    upload_session.content_type)


    # - Upload to MinIO
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
            raise HTTPException(502, f"Error uploading to MinIO: {str(e)}")
    # - URL
    url = get_presigned_url(full_object_path, 1)
        

    # 5. Persist metadata record 
    # - Define repo according to table or according to ext (same thing?)
    tab_name = upload_session.tab_name
    # - The entity for generic record is being built here and is being do particular in the called repo from service
    file = FileSave(
        id_file=serial,
        id_parent=parent_id,
        archivo_file=full_object_path,
        url_file=url
    )

    result = dispatch_service(tab_name, db, file, current_user)

    # - Mark upload as indeed completed
    mark_completed(db, upload_session)  # commit here

    # 6. Clean chunks — after commit
    clean_chunks(upload_id, chunks_in_disk, assembled_path)

    