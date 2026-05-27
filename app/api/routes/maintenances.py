from pydantic import UUID7

from fastapi import Optional, UploadFile, File, APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.services.maintenance_service import create_new_maintenance, update_existing, list_maintenances
from app.schemas.maintenance import MaintenanceCreate, MaintenanceUpdate

router = APIRouter(prefix="/maintenances")

@router.get("")
def get_maintenance(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):

    return list_maintenances(db, current_user, page, page_size)

@router.post("")
def create_maintenance(
    data: MaintenanceCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):

    return create_new_maintenance(
        db,
        data,
        current_user
    )

@router.patch("/{maintenance_id}")
async def update_maintenance(
    maintenance_id: UUID7,
    payload: MaintenanceUpdate = Depends(),
    initial_photo_file: Optional[UploadFile] = File(None), # Is the file per se. The column photo_path is the path
    # signature_receive_file: Optional[UploadFile] = File(None), # Is the file per se. The column (it's not necessary) is the path
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = {"initial_photo_file": initial_photo_file} # , "signature_receive_file": signature}
    return await update_existing(
        db, maintenance_id, payload, files, current_user
    )