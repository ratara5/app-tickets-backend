from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, Numeric, String, DateTime, Time, PrimaryKeyConstraint, ForeignKey
from sqlalchemy.orm import relationship, declarative_base 

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
    inicio_edicion = Column(DateTime)
    real_marcar_como = Column(String)

    # Campos para la hoja de trabajo
    observaciones = Column(String)
    nombre_recibe = Column(String)
    cedula_recibe = Column(Integer)
    cargo_recibe = Column(String)
    sap_recibe = Column(Integer)
    consecutivo_fus = Column(Integer)
    firma_recibe = Column(String)
    

    ticket = relationship("Ticket", back_populates="mantenimiento")
    pausas = relationship("Pausa", back_populates="mantenimiento")

class MantenimientoTecnico(Base, AuditMixin):
    __tablename__ = "mantenimientos_tecnicos"
    __table_args__ = (PrimaryKeyConstraint('id_mantenimiento', 'id_tecnico'),)

    id_mantenimiento = Column(Uuid, ForeignKey('mantenimientos.id_mantenimiento'), nullable=False)
    id_tecnico = Column(Integer, ForeignKey('tecnicos.id_tecnico'), nullable=False)
    hora_entrada = Column(Time, nullable=False) 
    hora_salida = Column(Time, nullable=False)

class MantenimientoRepuesto(Base, AuditMixin):
    __tablename__ = "mantenimientos_repuestos"
    __table_args__ = (PrimaryKeyConstraint('id_mantenimiento', 'id_repuesto'),)

    id_mantenimiento = Column(Uuid, ForeignKey('mantenimientos.id_mantenimiento'), nullable=False)
    id_repuesto = Column(Integer, ForeignKey('repuestos.id_repuesto'), nullable=False)
    cantidad = Column(Numeric(6, 2), nullable=False)
