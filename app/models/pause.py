from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Pause(Base, AuditMixin):
    __tablename__ = "pauses"

    pause_id = Column(Integer, primary_key=True) # Type is no more UNIQUEID()
    maintenance_id = Column(Uuid, ForeignKey('maintenances.maintenance_id'), nullable=False)
    # pause_timestamp = Column(DateTime) # equals to created_at
    pause_reason = Column(String)

    maintenance = relationship("Maintenance", back_populates="pauses")

