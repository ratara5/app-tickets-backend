from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Uuid, func
from sqlalchemy.orm import relationship

from app.models.base import Base

from app.models.audit_mixin import AuditMixin


class Photo(Base, AuditMixin):
    __tablename__ = "photos"

    # Live declares photos.photo_id as text and save_photo writes a hex token
    # (secrets.token_hex(4)) into it. Declaring it Integer matched neither: on
    # SQLite an INTEGER PRIMARY KEY is a rowid alias, so inserting that string
    # raised "datatype mismatch" and aborted the photo insert.
    photo_id = Column(Text, primary_key=True)
    maintenance_id = Column(Uuid, ForeignKey("maintenances.maintenance_id"))
    photo_path = Column(String)
    # url_foto = Column(String)|
    processed = Column(Boolean)

    created_at = Column(
        DateTime,
        server_default=func.now(), # Delegating to postgres generates a timestamp
        nullable=False
    )

    maintenance = relationship("Maintenance", back_populates="photos")

