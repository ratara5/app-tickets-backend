from datetime import datetime

from sqlalchemy import Uuid, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, LargeBinary
from sqlalchemy.orm import relationship, declarative_base


Base = declarative_base()

"""
CREATE TABLE IF NOT EXISTS worksheets(
    worksheet_id INTEGER PRIMARY KEY,
    maintenance_id UUID,
	
    receiver_name VARCHAR(150),
    receiver_doc_id VARCHAR(50),
    receiver_position VARCHAR(100),
    receiver_sap VARCHAR(50),
    receiver_signature TEXT,
    receiver_signature_timestamp TIMESTAMP WITH TIME ZONE,
	
    sheet_number VARCHAR(30) UNIQUE,
    pdf_url VARCHAR(100),
    generated_at TIMESTAMP WITH TIME ZONE,
    closed BOOLEAN,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id)
);
"""

class Worksheet(Base):
    __tablename__ = "worksheets"

    worksheet_id = Column(Integer, primary_key=True)
    maintenance_id = Column(Uuid, ForeignKey("maintenances.maintenance_id"), unique=True, nullable=False)

    # Fields completed in the field
    receiver_name = Column(String(150))
    receiver_doc_id = Column(String(50)) 
    receiver_position = Column(String(100))
    receiver_sap = Column(String(50))
    receiver_signature = Column(Text) # base64 PNG
    receiver_signature_timestamp = Column(DateTime)

    # Snapshot / auditory
    sheet_number = Column(String(30), unique=True) 
    pdf_url = Column(String(500))
    generated_at = Column(DateTime)
    closed = Column(Boolean)   # Colum(Integer, default=0) 0=draft, 1=closed

    # Relation
    maintenance = relationship("Maintenance", back_populates="worksheet")

