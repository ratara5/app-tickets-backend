from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship, declared_attr


class AuditMixin:
    # Live declares these as timestamptz and nullable (real rows carry NULL,
    # e.g. photos.created_by). The model reproduces live so Alembic drift stays
    # empty; the app still populates them on write.
    created_at = Column(
        DateTime(timezone=True),
        default=func.now(), # App-side timestamp; keeps SQLite tests working
        nullable=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=True
    )
    created_by = Column(Integer, ForeignKey("fsm_users.user_id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("fsm_users.user_id"), nullable=True)

    @declared_attr
    def creator(cls): # Use: record.creator.user_name
        return relationship("FSMUser", foreign_keys=[cls.created_by])

    @declared_attr 
    def updater(cls): # Use: record.updater.email   
        return relationship("FSMUser", foreign_keys=[cls.updated_by])