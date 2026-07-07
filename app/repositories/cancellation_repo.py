from datetime import datetime, timezone

from app.models.cancellation import Cancellation


def save_cancellation(db, data, current_user):
    now = datetime.now(timezone.utc)
    cancellation = Cancellation(
        ticket_id=data.ticket_id,
        cancellation_reason=data.cancellation_reason,
        created_at=now,
        updated_at=now,
        created_by=current_user.user_id,
        updated_by=current_user.user_id,
    )

    db.add(cancellation)
    db.commit()
    db.refresh(cancellation)

    return cancellation

def get_cancellations(db, current_user, page: int = 1, page_size: int = 50):
    pass