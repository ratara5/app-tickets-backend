from datetime import datetime
from pydantic import UUID7

from sqlalchemy.orm import Session

from app.models.worksheet import Worksheet

def get_worksheet_by_maintenance_id(db: Session, maintenance_id: UUID7, current_user):
    return db.query(Worksheet).filter(Worksheet.maintenance_id == maintenance_id).first()
    

def create_worksheet(db: Session, maintenance_id: UUID7, current_user):
    ws = Worksheet(maintenance_id=maintenance_id)
    db.add(ws)
    db.flush()

def update_existing_ws(db: Session, ws: Worksheet, data: dict) -> Worksheet:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ws, field, value)
    ws.updated_at = datetime.now()

    db.commit()
    db.refresh(ws)

    return ws


def save_worksheet(db: Session, ws: Worksheet, path: str, number: str) -> Worksheet: # This is save repo
    # with an update query, automatic refresh is lost and it's necessary return another query (not practical). So, it's better dot notation here
    ws.sheet_number = number
    ws.pdf_path = path
    ws.generated_at = datetime.now()
    ws.closed = True

    db.commit()
    db.refresh(ws)
    
    return ws