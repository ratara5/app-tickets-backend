from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

from app.core.database import get_db
from app.core.storage import get_presigned_url

from app.schemas.worksheet import WorksheetUpsert, WorksheetOut

import app.services.worksheet_service as svc


router = APIRouter(prefix="/maintenances", tags=["worksheets"])

@router.get("/{maintenance_id}/worksheet", response_model=WorksheetOut)
def get_worksheet(maintenance_id: int, db: Session = Depends(get_db),
                  _ = Depends(get_current_user)):
    ws = svc._get_or_create_worksheet(maintenance_id, db)
    db.commit()
    return ws

@router.post("/{maintenance_id}/worksheet/generate-pdf")
def generate_pdf(maintenance_id: int, db: Session = Depends(get_db),
                 _ = Depends(get_current_user)):
    ws = svc.generate_pdf(maintenance_id, db)
    return {
        "sheet_number": ws.sheet_number,
        "url": get_presigned_url(object_name=ws.pdf_url, expires_hours=1),
        "generated_at": ws.generated_at,
    }

@router.patch("/{maintenance_id}/worksheet", response_model=WorksheetOut)
def update_worksheet(maintenance_id: int, data: WorksheetUpsert,
                     db: Session = Depends(get_db),
                     _ = Depends(get_current_user)):
    return svc.upsert_worksheet(maintenance_id, data, db)