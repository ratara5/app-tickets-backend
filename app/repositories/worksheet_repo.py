from datetime import datetime
from pydantic import UUID7

from sqlalchemy.orm import Session

from app.models.worksheet import Worksheet

def get_worksheet_by_maintenance_id(db: Session, maintenance_id: UUID7, current_user):
    return db.query(Worksheet).filter(Worksheet.maintenance_id == maintenance_id).first()
    

def create_worksheet(db: Session, maintenance_id: UUID7, current_user) -> Worksheet:
    ws = Worksheet(maintenance_id=maintenance_id, closed=False)
    db.add(ws)
    db.flush()
    return ws

def update_existing_ws(db: Session, ws: Worksheet, data) -> Worksheet:
    payload = data.model_dump()

    signature_ts = payload.get("receiver_signature_timestamp")
    if signature_ts:
        try:
            payload["receiver_signature_timestamp"] = datetime.fromisoformat(signature_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            payload["receiver_signature_timestamp"] = None

    for field, value in payload.items():
        setattr(ws, field, value)

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