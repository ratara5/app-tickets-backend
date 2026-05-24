from pydantic import BaseModel, UUID7
from typing import Optional

class FotoSave(BaseModel):

    id_foto: str
    id_mantenimiento: UUID7
    archivo_foto: Optional[str] = None
    url_foto: Optional[str] = None

