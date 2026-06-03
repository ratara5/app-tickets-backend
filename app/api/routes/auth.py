from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db

from app.schemas.auth import LoginRequest, TokenResponse

from app.services.auth_service import login_user


router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db=Depends(get_db)):
    token = login_user(db, data.email, data.password)
    if not token:
        raise HTTPException(401, "Invalid credentials")
    return {
        "access_token": token,
        "token_type": "bearer"
    }