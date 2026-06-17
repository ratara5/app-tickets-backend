from datetime import datetime, UTC

from jose import jwt
from sqlalchemy.orm import Session

from app.core.security import verify_password, hash_password, create_access_token
from app.core.settings import settings
from app.repositories.fsm_user_repo import get_user_by_email, create_user, get_user_by_id, update_user
from app.repositories.token_blacklist_repo import add_to_blacklist
from app.schemas.user import UserProfileResponse


def login_user(db: Session, email: str, password: str) -> str | None:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.passwd):
        return None
    return create_access_token(sub=str(user.user_id))

def register_user(db: Session, email: str, password: str, user_name: str) -> str:
    hashed = hash_password(password)
    user = create_user(db, email=email, user_name=user_name, passwd=hashed)
    return create_access_token(sub=str(user.user_id))

def logout_user(db: Session, token: str) -> None:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    jti = payload["jti"]
    exp = payload["exp"]
    expires_at = datetime.fromtimestamp(exp, tz=UTC)
    add_to_blacklist(db, jti=jti, expires_at=expires_at)

def get_user_profile(db: Session, user_id: int) -> UserProfileResponse | None:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    return UserProfileResponse.model_validate(user)

def update_user_profile(db: Session, user_id: int, user_name: str | None = None, photo_path: str | None = None) -> UserProfileResponse | None:
    user = update_user(db, user_id=user_id, user_name=user_name, photo_path=photo_path)
    if not user:
        return None
    return UserProfileResponse.model_validate(user)