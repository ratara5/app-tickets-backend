from fastapi import APIRouter, Depends, HTTPException, Security

from app.core.database import get_db
from app.api.deps import get_current_user, bearer

from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, LogoutResponse
from app.schemas.user import UserProfileResponse, UserUpdateRequest, RegisterResponse
from app.schemas.user import CurrentUser

from app.services.auth_service import login_user, register_user, logout_user, get_user_profile, update_user_profile
from app.repositories.fsm_user_repo import get_user_by_email


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

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db=Depends(get_db)):
    existing = get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(409, "Email already registered")
    token = register_user(db, email=data.email, password=data.password, user_name=data.user_name)
    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.post("/logout", response_model=LogoutResponse)
def logout(
    credentials=Security(bearer),
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    logout_user(db, credentials.credentials)
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserProfileResponse)
def get_me(
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    profile = get_user_profile(db, current_user.user_id)
    if not profile:
        raise HTTPException(404, "User not found")
    return profile

@router.put("/me", response_model=UserProfileResponse)
def update_me(
    data: UserUpdateRequest,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    profile = update_user_profile(
        db,
        user_id=current_user.user_id,
        user_name=data.user_name,
        photo_path=data.photo_path,
    )
    if not profile:
        raise HTTPException(404, "User not found")
    return profile