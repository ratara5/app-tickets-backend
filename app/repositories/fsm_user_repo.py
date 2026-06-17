from sqlalchemy.orm import Session

from app.models.fsm_user import FSMUser


def get_user_by_email(db: Session, email: str) -> FSMUser | None:
    return db.query(FSMUser).filter(FSMUser.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> FSMUser | None:
    return db.query(FSMUser).filter(FSMUser.user_id == user_id).first()

def create_user(db: Session, email: str, user_name: str, passwd: str, user_role: str = "TECHNICIAN") -> FSMUser:
    user = FSMUser(email=email, user_name=user_name, passwd=passwd, user_role=user_role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def update_user(db: Session, user_id: int, user_name: str | None = None, photo_path: str | None = None) -> FSMUser | None:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    if user_name is not None:
        user.user_name = user_name
    if photo_path is not None:
        user.photo_path = photo_path
    db.commit()
    db.refresh(user)
    return user