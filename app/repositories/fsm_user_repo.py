from app.models.fsm_user import FSMUser


def get_user_by_email(db, email: str):
    return db.query(FSMUser).filter(FSMUser.email == email).first()