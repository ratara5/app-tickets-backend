from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship

from app.models.base import Base

from app.models.audit_mixin import AuditMixin


class Photo(Base, AuditMixin):
    __tablename__ = "photos"

    photo_id = Column(Integer, primary_key=True)
    maintenance_id = Column(Integer, ForeignKey("maintenances.maintenance_id"))
    photo_path = Column(String)
    # url_foto = Column(String)|
    processed = Column(Boolean)

    created_at = Column(
        DateTime,
        server_default=func.now(), # Delegating to postgres generates a timestamp
        nullable=False
    )

    maintenance = relationship("Maintenance", back_populates="photos")

