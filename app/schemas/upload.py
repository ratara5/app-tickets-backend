from pydantic import BaseModel, UUID7
from typing import Optional


class UploadInitRequest(BaseModel):
    parent_tab: str       # para esta app la entidad padre será el mantenimiento...
    parent_id: UUID7        # ...
    tab_name: str           # "fotos", "pdfs", "videos"... "tablas hijas"
    col_name: str           # "archivo_foto_inicio", "firma_recibe", "archivo_foto", etc.
    content_type: str       # "image/jpeg", "application/pdf", etc.
    total_size: int         # bytes totales
    total_chunks: int       # cuántos chunks enviará el cliente
    # tipo: str             # El mismo col_name?

class UploadInitResponse(BaseModel):
    upload_id: str          # UUID — el cliente lo guarda para reanudar, por qué no tipo UUID?
    chunk_size: int         # tamaño esperado por chunk (1 MB)
    next_chunk: int         # siempre 0 al iniciar

class ChunkResponse(BaseModel):
    upload_id: str
    chunk_index: int
    received_chunks: int
    total_chunks: int

class ChunkStatusResponse(BaseModel):
    upload_id: str
    received_chunks: int
    total_chunks: int
    is_complete: bool
    file_url: Optional[str] = None