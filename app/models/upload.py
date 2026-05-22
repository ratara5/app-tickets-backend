from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

import uuid
from uuid6 import uuid7 

Base = declarative_base()



"""
CREATE TABLE IF NOT EXISTS uploads_sessions (
    upload_id        UUID        PRIMARY KEY DEFAULT uuid_generate_v7(),
    entity_id        INTEGER     NOT NULL,
	user_email       TEXT        NOT NULL,
    filename         TEXT        NOT NULL,
    content_type     TEXT        NOT NULL,           
    total_size       INTEGER     NOT NULL,          
    total_chunks     INTEGER     NOT NULL,
    received_chunks  INTEGER     NOT NULL,
	tab_name         TEXT        ,
    col_name         TEXT        NOT NULL,                          
    expires_at       TIMESTAMPTZ NOT NULL
);
"""

class UploadSession(Base):
    __tablename__ = "upload_sessions"

    upload_id = Column(Uuid, primary_key=True, default=uuid7),   
    entity_id = Column(Integer), 
    user_email = Column(String),
    filename = Column(String),      
    content_type = Column(String),             
    total_size = Column(Integer),              
    total_chunks = Column(Integer),  
    received_chunks = Column(Integer), 
    tab_name = Column(String),      
    col_name = Column(String),                                
    expires_at  = Column(DateTime)  
