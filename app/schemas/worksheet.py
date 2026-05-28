from typing import Optional
from datetime import datetime

from pydantic import BaseModel, UUID7


class WorksheetUpsert(BaseModel):
    """From mobile app (technician fills in field)."""
    receiver_name: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_doc_id: Optional[str] = None
    receiver_position: Optional[str] = None
    receiver_sap: Optional[str] = None
    receiver_signature: Optional[str] = None # base64
    receiver_signature_timestamp: Optional[str] = None

class WorksheetOut(BaseModel):
    worksheet_id: int
    maintenance_id: UUID7

    receiver_name: Optional[str]
    receiver_doc_id: Optional[str]
    receiver_position: Optional[str]
    receiver_sap: Optional[str]
    receiver_signature: Optional[str]
    receiver_signature_date: Optional[datetime]

    sheet_number: Optional[str] 
    pdf_url: Optional[str] 
    generated_at: Optional[datetime] 
    closed: int

class Config:
    from_attributes = True


