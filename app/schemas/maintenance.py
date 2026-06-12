from decimal import Decimal
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, UUID7, ConfigDict


class SpareIn(BaseModel):
    spare_id: int
    qty: Decimal

class SpareOut(BaseModel):
    spare_id: int
    name: str
    price: Decimal
    qty: Decimal

class TechnicianIn(BaseModel):
    technician_id: int
    start_hour: datetime 
    end_hour: datetime

class TechnicianOut(BaseModel):
    technician_id: int
    technician_name: str
    start_hour: datetime 
    end_hour: datetime

# class PhotoIn(BaseModel): # The photos are uploaded apart (by file schema) of the maintenance saved process
    # photo_id: int

class PhotoOut(BaseModel):
    photo_id: int
    photo_url: str

class MaintenanceCreate(BaseModel):
    maintenance_id: UUID7
    ticket_id: int
    maintenance_date: date

class MaintenanceUpdate(BaseModel):
    # ticket_id: int # Already exists, it shouldn't come from client
    maintenance_date: Optional[date] = None # You can choose whether or not to send it; it will still be automatically assigned when saving if you don't send it.
    # initial_photo_path: str # Come via UploaFfile

    # Mandatory fields in order to updates existing maintenance
    maintenance_description: str

    # computed or derived fields (within service)
    # maintenance_start: Optional[datetime] = None # This field doesn't exist more  # automatically assign when update
    # start_edicion: Optional[datetime] = None
    # labsdl_id: Optional[int] = None 
    # real_mark_as: Optional[str] = None

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