import os
from tipyng import Optional

from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.api.routes import get_current_user
from app.core.database import get_db

from app.schemas.upload import (UploadInitRequest, 
                               UploadInitResponse, 
                               ChunkStatusResponse)

from app.services.upload_service import init_upload_service, upload_chunk_service

router = APIRouter(prefix="/uploads", tags=["uploads"])

# ── 1. Iniciar upload ─────────────────────────────────────────────────────────
@router.post("/init", response_model=UploadInitResponse)
async def init_upload(
    payload: UploadInitRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # route ->service -> repository
    # route <- service <- UploadInitResponse(no desde repo, sino creada en service)
    upload_init_response = await init_upload_service(db, current_user, payload)
    return upload_init_response

# ── 2. Subir chunk ────────────────────────────────────────────────────────────
@router.post("/chunk")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
    x_chunk_checksum: Optional[str] = Header(None),  # MD5 opcional
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chunk_response = await upload_chunk_service(db, 
                                                current_user, 
                                                upload_id, 
                                                chunk_index, 
                                                chunk, 
                                                x_chunk_checksum)
    return chunk_response
