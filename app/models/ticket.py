from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    String,
    Date,
    Boolean,
    ForeignKey,
    Text,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from app.models.base import Base

from app.models.audit_mixin import AuditMixin


# Live stores these as PostgreSQL ENUM types (priority_type, status_type).
# Declaring them as plain String produced permanent Alembic drift; the SQLite
# variant keeps the in-memory test database on VARCHAR.
priority_type = SAEnum("LOW", "MEDIUM", "HIGH", name="priority_type").with_variant(
    String(), "sqlite"
)
status_type = SAEnum(
    "OPEN", "ASSIGNED", "CANCELLED", "IN PROGRESS", "PAUSED", "CLOSED", "SIGNED",
    name="status_type",
).with_variant(String(), "sqlite")


class Ticket(Base, AuditMixin):
    __tablename__ = "tickets"

    ticket_id = Column(Integer, primary_key=True)
    ticket_date = Column(Date)
    ticket_description = Column(String)
    priority = Column(priority_type)
    status = Column(status_type)
    market_id = Column(Integer, ForeignKey("markets.market_id"))
    equipment_id = Column(Integer, ForeignKey("equipments.equipment_id"))
    assigned_to = Column(Integer, ForeignKey("technicians.technician_id"), nullable=True) # One ticket may have assigned_to null 

    # relationships
    maintenance = relationship("Maintenance", back_populates="ticket", uselist=False) # One maintenance One ticket # It's not necessary get maintenance from ticket. So there is not maintenance field
    market = relationship("Market", back_populates="tickets") # One market Many tickets
    equipment = relationship("Equipment", back_populates="tickets") # One equipment Many tickets
    cancellation = relationship("Cancellation", back_populates="ticket", uselist=False) # One cancellation One ticket # It's not necessary get cancellation from ticket. So there is not cancellation field
    technician = relationship("Technician", back_populates="tickets") # One technician Many tickets
    add_wkd = relationship("AddWkd", back_populates="ticket", uselist=False) # One addwkd One ticket 

class AddWkd(Base, AuditMixin):
    __tablename__ = "adticketswkd"

    ticket_id = Column(Integer, ForeignKey("tickets.ticket_id"), primary_key=True)

    operation_percentage = Column(Numeric)
    market_temperature = Column(Numeric)
    operation_damage = Column(Boolean)
    completed = Column(Boolean)
    observations_wkd = Column(Text)

    # relationships
    ticket = relationship("Ticket", back_populates="add_wkd")
    
