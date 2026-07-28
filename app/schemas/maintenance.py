from decimal import Decimal
from datetime import date, datetime, time
from typing import Optional, List

from pydantic import BaseModel, UUID7, ConfigDict

from app.schemas.master import SpareResponse, TechnicianResponse


class SpareIn(BaseModel):
    spare_id: int
    qty: Decimal

class SpareOut(SpareResponse):
    qty: Decimal

class TechnicianIn(BaseModel):
    technician_id: int
    start_hour: time 
    end_hour: time

class TechnicianOut(TechnicianResponse):
    start_hour: time 
    end_hour: time

# class PhotoIn(BaseModel): # The photos are uploaded apart (by file schema) of the maintenance saved process
    # photo_id: int

class PhotoOut(BaseModel):
    photo_id: int
    photo_url: str

class MaintenanceCreate(BaseModel):
    maintenance_id: UUID7
    ticket_id: int
    maintenance_date: datetime

class MaintenanceUpdate(BaseModel):
    # ticket_id: int # Already exists, it shouldn't come from client
    maintenance_date: Optional[date] = None # You can choose whether or not to send it; it will still be automatically assigned when saving if you don't send it.
    # initial_photo_path: str # Come via UploaFfile

    # Mandatory fields in order to updates existing maintenance
    maintenance_description: str

    # labsdl_id and initial_photo_path are set server-side from ticket_date and file upload

    # Campos técnicos (Technical columns) # These aren't neccesary
    # carpeta_soporte: Optional[str] = None
    # formato_soporte: Optional[str] = None
    # url_foto_inicio: Optional[str] = None
    # url_informe_soporte: Optional[str] = None
    
    # Children or maintenance parts
    spares: Optional[List[SpareIn]] = []
    technicians: Optional[List[TechnicianIn]] = []
    # photo_ids: Optional[List[int]] = [] # It's not necessary

class MaintenanceItemResponse(BaseModel):
    maintenance_id: UUID7
    ticket_id: int

    spares: Optional[List[SpareOut]] = []
    technicians: Optional[List[TechnicianOut]] = []

    initial_photo_url: Optional[str] = None # It's a presigned URL
    pdf_url: Optional[str] = None # It's a presigned URL

    photos: Optional[List[PhotoOut]] = [] # It contains presigned URLs

    model_config = ConfigDict(from_attributes=True)