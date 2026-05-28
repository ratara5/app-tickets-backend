from sqlalchemy import Column, Integer, Numeric, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base 
from sqlalchemy.sql import func

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Photo(Base, AuditMixin):
    __tablename__ = "photos"

    photo_id = Column(Integer, primary_key=True)
    maintenance_id = Column(Integer, ForeignKey("maintenances.maintenances_id"))
    photo_path = Column(String)
    # url_foto = Column(String)
    processed = Column(Boolean)

    created_at = Column(
        DateTime,
        server_default=func.now(), # Delegating to postgres generates a timestamp
        nullable=False
    )

    maintenance = relationship("Maintenance", back_populates="photos")

