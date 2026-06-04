from enum import Enum

from pydantic import BaseModel, ConfigDict


class UserRole(str, Enum):
    technician = "TECHNICIAN"
    director = "DIRECTOR"
    administrator = "ADMINISTRATOR"

class CurrentUser(BaseModel):
    user_id: int
    email: str
    user_role: str

    model_config = ConfigDict(from_attributes=True)