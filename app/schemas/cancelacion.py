from pydantic import BaseModel

class CancelacionRequest(BaseModel):

    motivo_cancelacion: str

