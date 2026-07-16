from sqlalchemy import Column, Integer, String, Uuid, ForeignKey
from sqlalchemy.orm import declarative_base, relationship 

from app.models.base import Base

from app.models.audit_mixin import AuditMixin


class Pause(Base, AuditMixin):
    __tablename__ = "pauses"

    pause_id = Column(Integer, primary_key=True, autoincrement=True) # Type is no more UNIQUEID()
    maintenance_id = Column(Uuid, ForeignKey("maintenances.maintenance_id"), nullable=False)
    # pause_timestamp = Column(DateTime) # equals to created_at
    pause_reason = Column(String)

    maintenance = relationship("Maintenance", back_populates="pauses")

