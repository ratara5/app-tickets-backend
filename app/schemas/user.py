from datetime import datetime
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

class UserProfileResponse(BaseModel):
    user_id: int
    email: str
    user_name: str
    user_role: str
    photo_path: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserUpdateRequest(BaseModel):
    user_name: str | None = None
    photo_path: str | None = None

class RegisterResponse(BaseModel):
    user_id: int
    email: str
    user_name: str
    user_role: str

    model_config = ConfigDict(from_attributes=True)