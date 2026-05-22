from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, Numeric, String, DateTime, PrimaryKeyConstraint, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class MantenimientoRepuesto(Base, AuditMixin):
    __tablename__ = "mantenimientos_repuestos"
    __table_args__ = (PrimaryKeyConstraint('id_mantenimiento', 'id_repuesto'),)

    id_mantenimiento = Column(Uuid, ForeignKey('mantenimientos.id_mantenimiento'), nullable=False)
    id_repuesto = Column(Integer, ForeignKey('repuestos.id_repuesto'), nullable=False)
    cantidad = Column(Numeric(6, 2), nullable=False)

