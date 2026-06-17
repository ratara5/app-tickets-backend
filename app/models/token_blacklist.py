from sqlalchemy import Column, String, DateTime

from app.models.base import Base


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    jti = Column(String(36), primary_key=True)
    expires_at = Column(DateTime, nullable=False)
