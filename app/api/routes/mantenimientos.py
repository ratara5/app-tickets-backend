from fastapi import APIRouter, Depends

from app.api.routes import get_current_user
from app.core.database import get_db
from app.services.mantenimiento_service import list_mantenimientos

router = APIRouter(prefix="/mantenimientos")

@router.get("")
def get_mantenimientos(
    current_user = Depends(get_current_user),
    db = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):

    return list_mantenimientos(db, current_user, page, page_size)