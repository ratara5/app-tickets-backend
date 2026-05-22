from sqlalchemy import Column, Integer, Numeric, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base 

Base = declarative_base()

class Repuesto(Base):
    __tablename__ = "repuestos"

    id_repuesto = Column(Integer, primary_key=True)
    nombre = Column(String)
    unidades = Column(String)
    precio = Column(Numeric(10, 2))