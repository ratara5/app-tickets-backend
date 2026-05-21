from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Pausa(Base, AuditMixin):
    __tablename__ = "pausas"

    id_pausa = Column(Integer, primary_key=True) # Ya no es del tipo UNIQUEID()
    id_mantenimiento = Column(Uuid, ForeignKey('mantenimientos.id_mantenimiento'), nullable=False)
    fecha_hora_pausa = Column(DateTime, default=datetime.now()) # Inyectar TZ desde entorno y aplicar # TODO: Inyectar TZ desde entorno y aplicar datetime.now(tz=ZoneInfo("Continente/Ciudad")).strftime("%Y-%m-%d %H:%M:%S+00")
    motivo_pausa = Column(String)

    mantenimiento = relationship("Mantenimiento", back_populates="pausas")

