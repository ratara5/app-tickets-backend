from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, Numeric, String, DateTime, Time, PrimaryKeyConstraint, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class MantenimientoTecnico(Base, AuditMixin):
    __tablename__ = "mantenimientos_tecnicos"
    __table_args__ = (PrimaryKeyConstraint('id_mantenimiento', 'id_tecnico'),)

    id_mantenimiento = Column(Uuid, ForeignKey('mantenimientos.id_mantenimiento'), nullable=False)
    id_tecnico = Column(Integer, ForeignKey('tecnicos.id_tecnico'), nullable=False)
    hora_entrada = Column(Time, nullable=False) 
    hora_salida = Column(Time, nullable=False)

