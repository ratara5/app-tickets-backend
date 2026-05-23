import os, datetime
from pathlib import Path
import aiofiles

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.core.utils.dates import start_of_month

from app.models.upload import UploadSession

from app.core.settings import settings

chunk_dir = settings.chunk_dir

def get_upload_session(db: Session, upload_id: str, usuario_email) -> UploadSession:
    return db.query(UploadSession).filter(
        UploadSession.upload_id == upload_id,
        UploadSession.user_email == usuario_email,
    ).first()

def save_upload_session(db, upload_id, user_email, payload):
    upload_session = UploadSession(
        upload_id=upload_id,
        entity_id=payload.id_mantenimiento,
        user_email=user_email,
        content_type=payload.content_type,
        total_size=payload.total_size,
        total_chunks=payload.total_chunks,
        received_chunks=0,
        tab_name=payload.tab_name,
        col_name=payload.col_name,
        expires_at=datetime.now() + datetime.timedelta(hours=24)
    )
    db.add(upload_session)
    db.commit()

    return upload_session

def mark_completed(db: Session, upload_session: UploadSession):
    upload_session.completado = True
    upload_session.completado_en = datetime.now()
    db.commit()

# Las siguientes 4 deberían estar aquí (o en otro repo o en core/disk.py?)
def get_chunks_on_disk(upload_id: str) -> list[str]:
    return sorted([
        f for f in os.listdir(chunk_dir)
        if f.startswith(f"{upload_id}_")
    ])

def get_chunks_missing(upload_id: str, total_chunks: int) -> list[int]:
    chunks_in_disk = get_chunks_on_disk(upload_id)
    chunk_names = set(chunks_in_disk)
    return [
        i for i in range(total_chunks)
        if f"{upload_id}_{i:04d}" not in chunk_names
    ]


async def assemble_chunks(upload_id: str, chunks: list[str]) -> str: 
    """Ensambla chunks en un archivo temporal. Retorna la ruta."""
    output_path = os.path.join(chunk_dir, f"{upload_id}_assembled")
    async with aiofiles.open(output_path, "wb") as out:
        for chunk_name in chunks:
            chunk_path = os.path.join(chunk_dir, chunk_name)
            async with aiofiles.open(chunk_path, "rb") as f:
                await out.write(await f.read())
    return output_path

def clean_chunks(upload_id: str, chunks: list[str], assembled_path: str):
    for chunk_name in chunks:
        os.remove(os.path.join(chunk_dir, chunk_name))
    if os.path.exists(assembled_path):
        os.remove(assembled_path)
