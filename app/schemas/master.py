from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TechnicianResponse(BaseModel):
    technician_id: int
    # user_id: int
    user_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SpareResponse(BaseModel):
    spare_id: int
    spare_name: str
    # unit: Optional[str] = None
    price: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class MarketResponse(BaseModel):
    market_id: int
    market_name: str
    city: Optional[str] = None
    transport_cost: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class EquipmentResponse(BaseModel):
    equipment_id: int
    equipment_name: str

    model_config = ConfigDict(from_attributes=True)


class LabsdlResponse(BaseModel):
    labsdl_id: int
    labsdl_name: str
    labsdl_description: Optional[str] = None
    hourly_rate: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)
