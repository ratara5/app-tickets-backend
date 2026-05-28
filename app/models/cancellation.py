from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Cancellation(Base, AuditMixin):
    __tablename__ = "cancellations"

    ticket_id = Column(Integer, ForeignKey("tickets.ticket_id"), primary_key=True)
    # cancellation_date = Column(DateTime) # Equals to created_at ** It's not the same case for tickets (because those are writting from out of ORM) and for maintenances (because those are probably updating in several times and the date are include in these updates)
    cancellation_reason = Column(String)
    # cancellation_responsible = Column(Integer, ForeignKey("fsm_users.user_id")) # The same creator

    ticket = relationship("Ticket", back_populates="cancellation")
