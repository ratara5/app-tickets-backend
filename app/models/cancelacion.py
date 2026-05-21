from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Cancelacion(Base, AuditMixin):
    __tablename__ = "cancelaciones"

    nro_ticket = Column(Integer, ForeignKey("tickets.nro_ticket"), primary_key=True)
    fecha_cancelacion = Column(DateTime, default=datetime.now().strftime("%d/%m/%Y")) # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad")).strftime("%d/%m/%Y")
    motivo_cancelacion = Column(String)
    responsable_cancelacion = Column(String)

    ticket = relationship("Ticket", back_populates="cancelacion")
