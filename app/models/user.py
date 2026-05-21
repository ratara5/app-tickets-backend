
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship, Mapped, mapped_column
from sqlalchemy.orm import declarative_base 

Base = declarative_base()

class User(Base):
    __tablename__ = "usuarios"

    email = Column(String, primary_key=True)

    nombre = Column(String)

    role: Mapped[str] = mapped_column("rol")    

    archivo_foto = Column(String)

    tecnico = relationship(
        "Tecnico",
        uselist=False
    )