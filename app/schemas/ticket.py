from enum import Enum

from pydantic import BaseModel, Optional


class TicketCreate(BaseModel):
    ticket_id: str
    priority: str 
    ticket_date: str
    ticket_description: str
    status: str

class TicketStatus(str, Enum):
    open = "OPEN"
    assigned = "ASSIGNED"
    in_progress = "IN PROGRESS"
    paused = "PAUSED"
    cancelled = "CANCELLED"
    closed = "CLOSED"

class AssignRequest(BaseModel):
    technician_id: Optional[int] = None