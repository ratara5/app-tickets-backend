from sqlalchemy import Column, Integer, Numeric, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship, declarative_base 
from sqlalchemy.sql import func

from app.models.audit_mixin import AuditMixin

Base = declarative_base()

class Foto(Base, AuditMixin):
    __tablename__ = "fotos"

    id_foto = Column(Integer, primary_key=True)
    id_mantenimiento = Column(Integer, ForeignKey("mantenimientos.id_mantenimiento"))
    archivo_foto = Column(String)
    url_foto = Column(String)
    # procesado = Column(Boolean)

    created_at = Column(
        DateTime,
        server_default=func.now(), # Delega a postgres la generación del timestamp
        nullable=False
    )

    mantenimiento = relationship("Mantenimiento", back_populates="fotos")

