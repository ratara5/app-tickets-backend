from pydantic import BaseModel
from app.schemas.maintenance import MaintenanceUpdate


class PauseRequest(MaintenanceUpdate):
    pause_reason: str