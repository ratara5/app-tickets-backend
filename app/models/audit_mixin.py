from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship, declared_attr


class AuditMixin:
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(), # App-side timestamp; keeps SQLite tests working
        nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(),
        onupdate=lambda: datetime.now(),
        nullable=False
    )
    created_by = Column(Integer, ForeignKey("fsm_users.user_id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("fsm_users.user_id"), nullable=False)

    @declared_attr
    def creator(cls): # Use: record.creator.user_name
        return relationship("FSMUser", foreign_keys=[cls.created_by])

    @declared_attr 
    def updater(cls): # Use: record.updater.email   
        return relationship("FSMUser", foreign_keys=[cls.updated_by])