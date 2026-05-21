from pydantic import BaseModel

class PausaRequest(BaseModel):

    motivo_pausa: str

