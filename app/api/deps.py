from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials 
from jose import JWTError

from app.core.security import decode_token


bearer = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer)
):
    try:
        payload = decode_token(credentials.credentials)
        return payload["sub"]
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")