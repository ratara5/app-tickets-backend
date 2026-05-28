from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, relationship, Mapped, mapped_column
from sqlalchemy.orm import  declarative_base 
from sqlalchemy.sql import func

Base = declarative_base()

class FSMUser(Base):
    __tablename__ = "fsm_users"

    user_id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    user_name = Column(String)
    passwd   = Column(String(255), nullable=False)        # hash, never plain text
    user_role = Column(String) # : Mapped[str] = mapped_column("rol")    
    photo_path = Column(String)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    technician = relationship("Technician", back_populates="fsm_user", uselist=False)
    uploads_sessions = relationship("UploadSession", back_populates="fsm_user")