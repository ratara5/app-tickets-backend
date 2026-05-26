from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey, Text, LargeBinary
from sqlalchemy.orm import relationship, declarative_base


Base = declarative_base()

"""
CREATE TABLE IF NOT EXISTS worksheets(
    worksheet_id INTEGER PRIMARY KEY,
    id_mantenimiento UUID,
	
    receiver_name VARCHAR(150),
    receiver_doc_id VARCHAR(50),
    receiver_position VARCHAR (100),
    receiver_sap VARCHAR(50),
    receiver_signature TEXT,
    receiver_signature_date TIMESTAMP WITH TIME ZONE,
	
    sheet_number VARCHAR(30) UNIQUE,
    pdf_url VARCHAR(100),
    generated_at TIMESTAMP WITH TIME ZONE,
    closed INTEGER DEFAULT 0,

    FOREIGN KEY (id_mantenimiento) REFERENCES mantenimientos(id_mantenimiento)
);
"""

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

