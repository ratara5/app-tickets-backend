from pydantic import BaseModel


class PauseRequest(BaseModel):
    pause_reason: str