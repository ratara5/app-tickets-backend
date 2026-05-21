from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base 

import uuid
from uuid6 import uuid7 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Mantenimiento(Base, AuditMixin):
    __tablename__ = "mantenimientos"

    id_mantenimiento = Column(Uuid, primary_key=True, default=uuid7)
    nro_ticket = Column(Integer, ForeignKey("tickets.nro_ticket"))
    fecha_trabajo = Column(DateTime)
    descripcion_mantenimiento = Column(String)
    tipo_jornada = Column(Integer, ForeignKey("jornadas.id_jornada"))
    carpeta_soporte = Column(String)
    formato_soporte = Column(String)
    archivo_foto_inicio = Column(String)
    url_foto_inicio = Column(String)
    url_informe_soporte = Column(String)
    inicio_mantenimiento = Column(DateTime)
    real_marcar_como = Column(String)
    observaciones = Column(String)
    nombre_recibe = Column(String)
    cedula_recibe = Column(Integer)
    cargo_recibe = Column(String)
    sap_recibe = Column(Integer)
    consecutivo_fus = Column(Integer)
    firma_recibe = Column(String)
    inicio_edicion = Column(DateTime)

    ticket = relationship(
        "Ticket",
        back_populates="mantenimiento"
    )