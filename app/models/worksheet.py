from sqlalchemy import Uuid, Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


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
    pdf_path = Column(String(500)) # Minio path
    generated_at = Column(DateTime)
    closed = Column(Boolean, default=False)   # 0=draft, 1=closed (PDF generated)

    # Relation
    maintenance = relationship("Maintenance", back_populates="worksheet")

    @property
    def receiver_signature_date(self):
        return self.receiver_signature_timestamp

