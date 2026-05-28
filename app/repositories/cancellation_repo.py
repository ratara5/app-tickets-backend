from datetime import datetime

from app.models.cancellation import Cancellation


def save_cancellation(db, data, current_user):

    cancellation = Cancellation(
        ticket_id=data.ticket_id,
        # cancellation_date=data.cancellation_date or datetime.now().strftime("%d/%m/%Y"), # equals to created_at # TODO: To inject TZ from environment and apply .strftime("%d/%m/%Y")
        cancellation_reason=data.cancellation_reason,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00") # overwritting auditmixin TODO: To inject TZ from environment and apply .strftime("%Y-%m-%d %H:%M:%S+00")
    )

    db.add(cancellation)
    db.commit()
    db.refresh(cancellation)

    return cancellation

def get_cancellations(db, current_user, page: int = 1, page_size: int = 50):
    pass