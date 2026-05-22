import datetime

from sqlalchemy import or_, and_
from app.models.ticket import Ticket
from app.core.utils.dates import start_of_month

from app.models.upload import UploadSession

def save_upload_session(db, upload_id, user_email, payload):
    upload_session = UploadSession(
        upload_id=upload_id,
        entity_id=payload.id_mantenimiento,
        user_email=user_email,
        filename=payload.filename,
        content_type=payload.content_type,
        total_size=payload.total_size,
        total_chunks=payload.total_chunks,
        chunks_recibidos=0,
        tipo=payload.tipo,
        expires_at=datetime.now() + datetime.timedelta(hours=24)
    )
    db.add(upload_session)
    db.commit()

    return upload_session