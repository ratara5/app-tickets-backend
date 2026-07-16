from typing import List, Optional
from pydantic import UUID7

from fastapi import UploadFile, File, APIRouter, Depends, Form
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db

from app.schemas.maintenance import MaintenanceCreate, MaintenanceUpdate, MaintenanceItemResponse
from app.schemas.ticket import TicketItemResponse
from app.schemas.pause import PauseRequest

import app.services.maintenance_service as maintenance_svc


router = APIRouter(prefix="/maintenances")

@router.get("", response_model=List[MaintenanceItemResponse])
def get_maintenances(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return maintenance_svc.list_maintenances(db, current_user, page, page_size)

@router.get("/{maintenance_id}", response_model=MaintenanceItemResponse)
def get_maintenance(
    maintenance_id: UUID7,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return maintenance_svc.get_maintenance(db, maintenance_id, current_user)

@router.post("", response_model=MaintenanceCreate)
def create_maintenance(
    data: MaintenanceCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    return maintenance_svc.create_new_maintenance(
        db,
        data,
        current_user
    )

@router.patch("/{maintenance_id}", response_model=MaintenanceItemResponse)
async def update_maintenance(
    maintenance_id: UUID7,
    payload: str = Form(...),
    initial_photo_file: Optional[UploadFile] = File(None), # Is the file per se. The column photo_path is the path
    # signature_receive_file: Optional[UploadFile] = File(None), # Is the file per se. The column (it's not necessary) is the path
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = MaintenanceUpdate.model_validate_json(payload)
    files = {"initial_photo_file": initial_photo_file} # , "signature_receive_file": signature}
    return await maintenance_svc.update_existing(
        db, maintenance_id, data, current_user, files
    )

@router.patch("/{maintenance_id}/pause", response_model=TicketItemResponse)
async def pause(maintenance_id: UUID7, 
          payload: str = Form(...),
          initial_photo_file: Optional[UploadFile] = File(None), # Is the file per se. The column photo_path is the path
          db: Session = Depends(get_db),
          current_user = Depends(get_current_user)):
    data = PauseRequest.model_validate_json(payload)
    files = {"initial_photo_file": initial_photo_file}
    return await maintenance_svc.pause_and_update(
        db, maintenance_id, data, current_user, files
    )

@router.delete("/{maintenance_id}", status_code=204)
def del_maintenance(maintenance_id: UUID7, 
               db: Session = Depends(get_db), 
               current_user = Depends(get_current_user)):
    return maintenance_svc.delete_maintenance(maintenance_id, current_user, db)