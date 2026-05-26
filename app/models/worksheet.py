from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey, Text, LargeBinary
from sqlalchemy.orm import relationship, declarative_base


Base = declarative_base()

class Worksheet(Base):
    __tablename__ = "worksheets"

    worksheet_id = Column(Integer, primary_key=True)
    id_mantenimiento = Column(Uuid, ForeignKey("mantenimientos.id_mantenimiento"), unique=True, nullable=False)

    # Datos a diligenciar en campo
    receiver_name = Column(String(150))
    receiver_doc_id = Column(String(50)) # Cédula
    receiver_position = Column(String(100)) # Cargo
    receiver_sap = Column(String(50))
    receiver_signature = Column(Text) # base64 PNG
    receiver_signature_date = Column(DateTime)

    # Snapshot / auditoría
    sheet_number = Column(String(30), unique=True) 
    pdf_url = Column(String(500))
    generated_at = Column(DateTime)
    closed = Column(Integer, default=0)   # 0=borrador, 1=cerrado

    # Relación
    mantenimiento = relationship("Mantenimiento", back_populates="worksheet")

