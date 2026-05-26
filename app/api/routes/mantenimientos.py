from pydantic import UUID7

from fastapi import Optional, UploadFile, File, APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.services.mantenimiento_service import create_new_mantenimiento, update_existing, list_mantenimientos
from app.schemas.mantenimiento import MantenimientoCreate, MantenimientoUpdate

router = APIRouter(prefix="/mantenimientos")

@router.get("")
def get_mantenimientos(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):

    return list_mantenimientos(db, current_user, page, page_size)

@router.post("")
def create_mantenimiento(
    data: MantenimientoCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):

    return create_new_mantenimiento(
        db,
        data,
        current_user
    )

@router.patch("/{id_mantenimiento}")
async def update_mantenimiento(
    id_mantenimiento: UUID7,
    payload: MantenimientoUpdate = Depends(),
    foto_inicio: Optional[UploadFile] = File(None), # Es el fichero como tal. La columna archivo_foto_inicio es el path
    firma: Optional[UploadFile] = File(None), # Es el fichero como tal. La columna firma_recibe es el path
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = {"archivo_foto_inicio": foto_inicio, "firma_recibe": firma}
    return await update_existing(
        db, id_mantenimiento, payload, files, current_user
    )