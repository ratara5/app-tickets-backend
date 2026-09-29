from sqlalchemy import Column, Uuid, DateTime

from app.models.base import Base


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    # Live stores jti as a real uuid column, but the code keys on the raw JWT
    # string, so the type is declared as_uuid=False to keep string binding.
    jti = Column(Uuid(as_uuid=False), primary_key=True)
    expires_at = Column(DateTime, nullable=False)
