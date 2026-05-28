# A Master Table (Master) contains high level info, (Customers, Products) structural data wich rarely change
# A Catalog Table (Reference/Lookup) contains low level info, descriptive/configuration, (Code, States) data wich very rarely change
# Here: Master includes Catalog

from datetime import datetime

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 


Base = declarative_base()

class Technician(Base):
    __tablename__ = "technicians"

    technician_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("fsm_users.user_id"), nullable=False, unique=True)
    # more fields ...

    fsm_user = relationship("FSMUser", back_populates="technician")
    # intermediate tables relationships (...2...)
    maintenances = relationship("MaintenanceTechnician", back_populates="technician")

class Spare(Base):
    __tablename__ = "spares"

    spare_id = Column(Integer, primary_key=True)
    spare_name = Column(String)
    unit = Column(String)
    price = Column(Numeric(10, 2))
    # It's not defined the relation with uom

    # intermediate tables relationships (...2...)
    maintenances = relationship("MaintenanceSpare", back_populates="spare")

class Market(Base):
    __tablename__ = "markets"

    market_id = Column(Integer, primary_key=True),
    market_name = Column(String)
    city = Column(String)    
    transport_cost = Column(Numeric(10, 2))

# Catalog
class Equipment(Base):
    __tablename__ = "equipments"

    equipment_id = Column(Integer, primary_key=True),
    equipment_name = Column(String)

# Catalog
class Labsdls(Base):
    __tablename__ = "labsdls"

    labsdl_id = Column(Integer, primary_key=True),
    labsdl_name = Column(String)
    labsdl_description = Column(String)
    hourly_rate = Column(Numeric(8, 2))









