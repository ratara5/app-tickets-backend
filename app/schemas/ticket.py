from pydantic import BaseModel, Optional
from enum import Enum

class TicketCreate(BaseModel):
    nro_ticket: str
    prioridad: str 
    fecha_ticket: str
    descripcion_ticket: str
    estado: str

class TicketEstado(str, Enum):
    abierto = "ABIERTO"
    asignado = "ASIGNADO"
    en_progreso = "EN PROGRESO"
    pausado = "PAUSADO"
    cancelado = "CANCELADO"
    ejecutado = "EJECUTADO"

class AssignRequest(BaseModel):
    tecnico_id: Optional[int] = None



