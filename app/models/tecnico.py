from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base 

Base = declarative_base()

class Tecnico(Base):
    __tablename__ = "tecnicos"

    id_tecnico = Column(Integer, primary_key=True)

    email = Column(String, ForeignKey("usuarios.email"))

    nombre = Column(String)