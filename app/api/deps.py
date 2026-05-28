from fastapi.security import HTTPBearer 
from fastapi import Depends
from jose import jwt

from app.core.database import get_db
from app.models.fsm_user import User

security = HTTPBearer()

def get_current_user(
    credentials = Depends(security),
    db = Depends(get_db)
):
    token = credentials.credentials
    payload = jwt.decode(...)
    user_id = payload["sub"]
    user = db.query(User).get(user_id)

    return user