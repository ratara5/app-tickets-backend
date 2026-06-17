from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    user_name: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LogoutResponse(BaseModel):
    message: str