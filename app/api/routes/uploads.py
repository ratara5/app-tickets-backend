from typing import Optional

from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db

from app.schemas.upload import (UploadInitRequest, 
                               UploadInitResponse, 
                               ChunkResponse,
                               ChunkStatusResponse)

import app.services.upload_service as upload_svc


router = APIRouter(prefix="/uploads", tags=["uploads"])


# ── 1. Start upload ─────────────────────────────────────────────────────────
@router.post("/init", response_model=UploadInitResponse)
async def init_upload(
    payload: UploadInitRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # route -> service -> repository
    # route <- service <- UploadInitResponse(no from repo, but created in service)
    upload_init_response = await upload_svc.init_upload(db, current_user, payload)
    return upload_init_response

# ── 2. Upload chunk ────────────────────────────────────────────────────────────
@router.post("/chunk", response_model=ChunkResponse)
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
    x_chunk_checksum: Optional[str] = Header(None),  # MD5 optional
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chunk_response = await upload_svc.upload_chunk(db, 
                                                current_user, 
                                                upload_id, 
                                                chunk_index, 
                                                chunk, 
                                                x_chunk_checksum)
    return chunk_response

# ── 3. Status upload  ────────────────────────────────────────────────────────────
@router.get("/status/{upload_id}", response_model=ChunkStatusResponse)
async def upload_status(
    upload_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    url, received_chunks, total_chunks = await upload_svc.get_status_upload( 
        db, upload_id, current_user
    )
    return ChunkStatusResponse(
        upload_id=upload_id,
        received_chunks=received_chunks,
        total_chunks=total_chunks,
        completed=False
    )

# ── 4. Upload complete ──────────────────────────────────────────────────────────
@router.post("/complete", response_model=ChunkStatusResponse)
async def complete_upload(
    upload_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    url, received_chunks, total_chunks = await upload_svc.complete_upload(
        db, upload_id, current_user
    )
    return ChunkStatusResponse(
        upload_id=upload_id,
        received_chunks=received_chunks,   # of session
        total_chunks=total_chunks,      # of session
        completed=True,
        file_url=url,
    )
