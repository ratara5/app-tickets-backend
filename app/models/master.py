# Una Tabla Maestra (Master) contiene info Alto nivel, (CLientes, Productos) datos estructurales que rara vez cambia
# Una Tabla Catálogo (Reference/Lookup) contiene info Bajo nivel, descriptivo/configuración, (Códigos, Estados) datos muy raramente cambian

from datetime import datetime

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 


Base = declarative_base()

class Tecnico(Base):
    __tablename__ = "tecnicos"

    id_tecnico = Column(Integer, primary_key=True)
    email = Column(String, ForeignKey("usuarios.email"))
    nombre = Column(String)

class Repuesto(Base):
    __tablename__ = "repuestos"

    id_repuesto = Column(Integer, primary_key=True)
    nombre = Column(String)
    unidades = Column(String)
    precio = Column(Numeric(10, 2))

class Tienda(Base):
    __tablename__ = "tiendas"

    nro_tienda = Column(Integer, primary_key=True),
    nombre_tienda = Column(String)
    ciudad = Column(String)    
    valor_transporte = Column(Numeric(10, 2))

class Equipo(Base):
    __tablename__ = "equipos"

    nro_equipo = Column(Integer, primary_key=True),
    nombre_equipo = Column(String)

class Jornadas(Base):
    __tablename__ = "jornadas"

    id_jornada = Column(Integer, primary_key=True),
    nombre_jornada = Column(String)
    descripcion_jornada = Column(String)
    tarifa_hora = Column(Numeric(8, 2))









