from datetime import datetime, timedelta, UTC
from uuid6 import uuid7

from jose import jwt
from passlib.context import CryptContext

from app.core.settings import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def create_access_token(sub: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": sub,
        "exp": expire,
        "jti": uuid7().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, settings.jwt_algorithm)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])