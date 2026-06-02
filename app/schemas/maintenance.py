from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, UUID7, ConfigDict


class SpareIn(BaseModel):
    maintenance_id: UUID7
    spare_id: int
    qty: int

class TechnicianIn(BaseModel):
    maintenance_id: UUID7
    technician_id: int
    start_hour: datetime 
    end_hour: datetime

class PhotoIn(BaseModel):
    photo_id: int
    maintenance_id: UUID7
    photo_url: str

class MaintenanceCreate(BaseModel):
    ticket_id: int

class MaintenanceUpdate(BaseModel):
    ticket_id: int # It's neccesary validates the ticket and its status before to allow maintenance updating
    maintenance_date: Optional[date] = None # You can choose whether or not to send it; it will still be automatically assigned when saving if you don't send it.

    # Mandatory fields in order to updates existing maintenance
    maintenance_description: str
    initial_photo_path: str

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

    ticket_date: date
    ticket_description: str
    status: str

    maintenance_date: date
    maintenance_description: str

    market_name: str
    equipment_name: str

    spares: Optional[List[SpareIn]] = []
    technicians: Optional[List[TechnicianIn]] = []

    initial_photo_url: Optional[str] = None # It's a presigned URL
    pdf_url: Optional[str] = None # It's a presigned URL

    photos: Optional[List[PhotoIn]] = [] # It contains presigned URLs

    model_config = ConfigDict(from_attributes=True)