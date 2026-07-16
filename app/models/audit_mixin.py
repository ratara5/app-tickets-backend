from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship, declared_attr


class AuditMixin:
    created_at = Column(
        DateTime,
        default=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00"), # Delegating to postgres generates a timestamp
        nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00"),
        onupdate=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00"),
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