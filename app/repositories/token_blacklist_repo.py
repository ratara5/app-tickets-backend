from datetime import datetime

from sqlalchemy.orm import Session

from app.models.token_blacklist import TokenBlacklist


def add_to_blacklist(db: Session, jti: str, expires_at: datetime) -> None:
    entry = TokenBlacklist(jti=jti, expires_at=expires_at)
    db.add(entry)
    db.commit()

def is_blacklisted(db: Session, jti: str) -> bool:
    return db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first() is not None
