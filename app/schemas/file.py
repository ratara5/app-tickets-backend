from typing import Optional

from pydantic import BaseModel, UUID7


class FileSave(BaseModel):
    file_id: str
    parent_id: UUID7
    file_path: Optional[str] = None # It's a minio path
    # url_file: Optional[str] = None