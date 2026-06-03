from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token

from repositories.fsm_user_repo import get_user_by_email


def login_user(db: Session, email: str, password: str) -> str | None:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.passwd): # user.passwd is the hashed password
        return None
    return create_access_token(sub=str(user.id))