from pydantic import BaseModel


class CancellationRequest(BaseModel):
    cancellation_reason: str