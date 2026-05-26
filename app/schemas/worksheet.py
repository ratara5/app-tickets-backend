from datetime import datetime
from typing import Optional

from pydantic import BaseModel, UUID7


class WorksheetUpsert(BaseModel):
    """Lo que llega desde la app móvil (técnico llena en campo)."""
    receiver_name: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_doc_id: Optional[str] = None
    receiver_position: Optional[str] = None
    receiver_sap: Optional[str] = None
    receiver_signature: Optional[str] = None # base64
    receiver_signature_date: Optional[str] = None

class WorksheetOut(BaseModel):
    worksheet_id: int
    id_mantenimiento: UUID7
    sheet_number: Optional[str] 
    pdf_url: Optional[str] 
    generated_at: Optional[datetime] 
    closed: int

    receiver_name: Optional[str]
    receiver_doc_id: Optional[str]
    receiver_position: Optional[str]
    receiver_sap: Optional[str]
    receiver_signature: Optional[str]
    receiver_signature_date: Optional[datetime]

class Config:
    from_attributes = True


