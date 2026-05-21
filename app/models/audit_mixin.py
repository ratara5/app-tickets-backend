from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

class AuditMixin:

    created_at = Column(
        DateTime,
        server_default=func.now(), # Inyectar TZ desde entorno
        nullable=False
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(), # Inyectar TZ desde entorno
        onupdate=func.now(),
        nullable=False
    )

    created_by = Column(String)

    updated_by = Column(String)