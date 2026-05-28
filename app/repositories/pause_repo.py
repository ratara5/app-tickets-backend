from datetime import datetime

from app.models.pause import Pause


def save_pause(db, data, current_user):

    pause = Pause(
        maintenance_id=data.maintenance_id,
        pause_reason=data.pause_reason,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00") # overwritting auditmixin TODO: To inject TZ from environment and apply .strftime("%Y-%m-%d %H:%M:%S+00")
    )

    db.add(pause)
    db.flush()
    db.refresh(pause)

    return pause

def get_pauses(db, current_user, page: int = 1, page_size: int = 50):
    pass