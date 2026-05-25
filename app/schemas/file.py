from pydantic import BaseModel, UUID7
from typing import Optional

class FileSave(BaseModel):

    id_file: str
    id_parent: UUID7
    archivo_file: Optional[str] = None # Es un path minio
    url_file: Optional[str] = None

