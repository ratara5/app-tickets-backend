from fastapi import APIRouter, HTTPException

from app.schemas.auth import LoginRequest
from app.services.auth_service import login_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(data: LoginRequest):

    # buscar usuario DB
    user = ...

    if not user:
        raise HTTPException(401, "Invalid credentials")

    token = login_user(user, data.password)

    if not token:
        raise HTTPException(401, "Invalid credentials")

    return {
        "access_token": token
    }