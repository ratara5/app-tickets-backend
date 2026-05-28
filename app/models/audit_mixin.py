from sqlalchemy import Column, DateTime, String, Integer, ForeignKey
from sqlalchemy.sql import declared_attr, relationship, func

class AuditMixin:

    created_at = Column(
        DateTime,
        server_default=func.now(), # Delegating to postgres generates a timestamp
        nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(), 
        onupdate=func.now(),
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