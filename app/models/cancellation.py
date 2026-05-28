from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Cancellation(Base, AuditMixin):
    __tablename__ = "cancellations"

    ticket_id = Column(Integer, ForeignKey("tickets.ticket_id"), primary_key=True)
    cancellation_date = Column(DateTime) 
    cancellation_reason = Column(String)
    # cancellation_responsible = Column(Integer, ForeignKey("fsm_users.user_id")) -- The same creator

    ticket = relationship("Ticket", back_populates="cancellation")
