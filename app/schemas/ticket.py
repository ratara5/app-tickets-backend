from decimal import Decimal
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TicketCreate(BaseModel):
    ticket_id: str
    ticket_date: str
    ticket_description: str
    priority: str 
    status: str
    market_id: int
    equipment_id: int

class TicketStatus(str, Enum):
    open = "OPEN"
    assigned = "ASSIGNED"
    in_progress = "IN PROGRESS"
    paused = "PAUSED"
    cancelled = "CANCELLED"
    closed = "CLOSED"

class AssignRequest(BaseModel):
    technician_id: Optional[int] = None

class TicketItemResponse(BaseModel):
    ticket_id: int

    ticket_date: date
    ticket_description: str

    priority: str
    status: str

    market_name: str
    market_city: str
    equipment_name: str

    assigned_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class AddWkdRequest(BaseModel):
    operation_percentage: Decimal
    market_temperature: Decimal
    operation_damage: bool  
    completed: bool
    observations_wkd: str