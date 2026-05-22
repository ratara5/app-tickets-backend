from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Ticket(Base, AuditMixin):
    __tablename__ = "tickets"

    nro_ticket = Column(Integer, primary_key=True)
    prioridad = Column(String)
    nro_tienda = Column(Integer, ForeignKey("tiendas.nro_tienda"))
    fecha_ticket = Column(DateTime)
    nro_equipo = Column(Integer, ForeignKey("equipos.nro_equipo"))
    descripcion_ticket = Column(String)
    estado = Column(String)
    asignado_a = Column(Integer, ForeignKey("tecnicos.id_tecnico"), nullable=True)

    mantenimiento = relationship("Mantenimiento", back_populates="ticket", uselist=False)
    cancelacion = relationship("Cancelacion", back_populates="ticket", uselist=False)