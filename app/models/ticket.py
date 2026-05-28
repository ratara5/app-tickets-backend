from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Ticket(Base, AuditMixin):
    __tablename__ = "tickets"

    ticket_id = Column(Integer, primary_key=True)
    priority = Column(String)
    market_id = Column(Integer, ForeignKey("markets.market_id"))
    ticket_date = Column(DateTime)
    equipment_id = Column(Integer, ForeignKey("equipments.equipment_id"))
    ticket_description = Column(String)
    status = Column(String)
    assigned_to = Column(Integer, ForeignKey("technicians.technician_id"), nullable=True)

    maintenance = relationship("Maintenance", back_populates="ticket", uselist=False)
    cancellation = relationship("Cancellation", back_populates="ticket", uselist=False)