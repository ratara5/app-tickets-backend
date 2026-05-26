from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.routes import get_current_user

from app.core.database import get_db
from app.core.storage import get_presigned_url

from app.schemas.worksheet import WorksheetUpsert, WorksheetOut

import app.services.worksheet_service as svc


router = APIRouter(prefix="/mantenimientos", tags=["worksheets"])

@router.get("/{id_mantenimiento}/worksheet", response_model=WorksheetOut)
def get_worksheet(id_mantenimiento: int, db: Session = Depends(get_db),
                  _=Depends(get_current_user)):
    ws = svc._get_or_create_worksheet(id_mantenimiento, db)
    db.commit()
    return ws

@router.post("/{id_mantenimiento}/worksheet/generar-pdf")
def generate_pdf(id_mantenimiento: int, db: Session = Depends(get_db),
                 _ = Depends(get_current_user)):
    ws = svc.generate_pdf(id_mantenimiento, db)
    return {
        "sheet_number": ws.sheet_number,
        "url": get_presigned_url(object_name=ws.pdf_url, expires_hours=1),
        "generated_at": ws.generated_at,
    }

@router.patch("/{id_mantenimiento}/worksheet", response_model=WorksheetOut)
def update_worksheet(id_mantenimiento: int, data: WorksheetUpsert,
                     db: Session = Depends(get_db),
                     _=Depends(get_current_user)):
    return svc.upsert_worksheet(id_mantenimiento, data, db)