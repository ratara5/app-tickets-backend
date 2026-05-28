from uuid6 import uuid7

import os, datetime
from pathlib import Path
import aiofiles

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.core.utils.dates import start_of_month
from app.core.settings import settings

from app.models.ticket import Ticket
from app.models.upload import UploadSession

chunk_dir = settings.chunk_dir


def get_upload_session(db: Session, 
                       upload_id: uuid7, 
                       user_id: int) -> UploadSession:
    return db.query(UploadSession).filter(
        UploadSession.upload_id == upload_id,
        UploadSession.user_id == user_id,
    ).first()

def save_upload_session(db, upload_id, user_id, payload):
    upload_session = UploadSession(
        upload_id=upload_id,
        user_id=user_id,

        parent_tab=payload.parent_tab, # "maintenances"...
        parent_id=payload.parent_id, # ...the value of maintenance_id
        tab_name=payload.tab_name,
        col_name=payload.col_name,
        
        content_type=payload.content_type,
        total_size=payload.total_size,
        total_chunks=payload.total_chunks,
        received_chunks=0,

        expires_at=datetime.now() + datetime.timedelta(hours=24)
    )
    db.add(upload_session)
    db.commit()

    return upload_session

def mark_completed(db: Session, upload_session: UploadSession):
    upload_session.completed = True
    upload_session.completed = datetime.now()
    db.commit()

# Should the next 4 be here (or in another repo or in core/disk.py)?
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
    """Assemble chunks in a temp file. Return path."""
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
