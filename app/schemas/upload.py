from typing import Optional

from pydantic import BaseModel, UUID7


class UploadInitRequest(BaseModel):
    parent_tab: str         # In this app, the parent tab will be 'maintenances'...
    parent_id: UUID7        # ...

    tab_name: str           # "photos", "pdfs", "videos"... "children tables"
    col_name: str           # "photo_file", etc. DON'T PUT HERE: fields into table per se ("initial_photo_path", "signature")
    
    content_type: str       # "image/jpeg", "application/pdf", etc.
    total_size: int         # total bytes
    total_chunks: int       # how many chunks will the client send?
    # tipo: str             # The same col_name?

class UploadInitResponse(BaseModel):
    upload_id: str          # UUID — the client save it for restart
    chunk_size: int         # expected size by chunk (1 MB)
    next_chunk: int         # 0 at start

class ChunkResponse(BaseModel):
    upload_id: str
    chunk_index: int
    received_chunks: int
    total_chunks: int

class ChunkStatusResponse(BaseModel):
    upload_id: str
    received_chunks: int
    total_chunks: int
    completed: bool
    file_url: Optional[str] = None