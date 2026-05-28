from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, Numeric, String, DateTime, Time, PrimaryKeyConstraint, ForeignKey
from sqlalchemy.orm import relationship, declarative_base 

from uuid6 import uuid7 

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Maintenance(Base, AuditMixin):
    __tablename__ = "maintenances"

    maintenance_id = Column(Uuid, primary_key=True, default=uuid7)
    ticket_id = Column(Integer, ForeignKey("tickets.ticket_id"))
    maintenance_date = Column(DateTime) 
    maintenance_description = Column(String)
    labsdl_id = Column(Integer, ForeignKey("labsdls.labsdl_id"))
    # carpeta_soporte = Column(String)
    # formato_soporte = Column(String)
    initial_photo_path = Column(String)
    # url_foto_inicio = Column(String)
    # url_informe_soporte = Column(String)
    maintenance_start = Column(DateTime)
    real_mark_as = Column(String)
    observations = Column(String)
    edition_start = Column(DateTime)

    # Campos para la hoja de trabajo
    # nombre_recibe = Column(String)
    # cedula_recibe = Column(Integer)
    # cargo_recibe = Column(String)
    # sap_recibe = Column(Integer)
    # consecutivo_fus = Column(Integer)
    # firma_recibe = Column(String)
    

    ticket = relationship("Ticket", back_populates="maintenance")
    pauses = relationship("Pause", back_populates="maintenance")
    photos = relationship("Photo", back_populates="maintenance")
    worksheet = relationship("Maintenance", back_populates="maintenance", uselist=False)

    # intermediate tables relationships (1...)
    technicians = relationship("MaintenanceTechnician", back_populates="maintenance")
    spares = relationship("MaintenanceSpare", back_populates="maintenance")

class MaintenanceTechnician(Base, AuditMixin):
    __tablename__ = "maintenances_technicians"
    __table_args__ = (PrimaryKeyConstraint('maintenance_id', 'technician_id'),)

    maintenance_id = Column(Uuid, ForeignKey('maintenances.maintenance_id'), nullable=False)
    technician_id = Column(Integer, ForeignKey('technicians.technician_id'), nullable=False)
    start_hour = Column(Time, nullable=False) 
    end_hour = Column(Time, nullable=False)

    # intermediate tables relationships (...3)
    maintenance = relationship("Maintenance", back_populates="technicians")
    technician  = relationship("Technician",  back_populates="maintenances")

class MaintenanceSpare(Base, AuditMixin):
    __tablename__ = "maintenances_spares"
    __table_args__ = (PrimaryKeyConstraint('maintenance_id', 'spare_id'),)

    maintenance_id = Column(Uuid, ForeignKey('maintenances.maintenance_id'), nullable=False)
    spare_id = Column(Integer, ForeignKey('spares.spare_id'), nullable=False)
    qty = Column(Numeric(6, 2), nullable=False)

    # intermediate tables relationships (...3)
    maintenance = relationship("Maintenance", back_populates="spares")
    spare  = relationship("Spare",  back_populates="maintenances")


