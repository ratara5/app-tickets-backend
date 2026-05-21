from pydantic import BaseModel

class TicketCreate(BaseModel):

    nro_ticket: str

    prioridad: str 

    fecha_ticket: str

    descripcion_ticket: str

    estado: str
