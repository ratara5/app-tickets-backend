from fastapi import Depends, HTTPException, Security
from sqlalchemy.orm import Session
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials 
from jose import JWTError

from app.core.security import decode_token
from app.core.database import get_db

from app.models.fsm_user import FSMUser

from app.schemas.user import CurrentUser


bearer = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
    db: Session = Depends(get_db)
) -> CurrentUser:
    try:
        payload = decode_token(credentials.credentials)
        user = db.query(FSMUser).filter(FSMUser.user_id == payload["sub"]).first() # query here is widely accepted for convenience
        if not user:
            raise HTTPException(401, "User not found")
        return CurrentUser.model_validate(user)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")