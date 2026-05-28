from sqlalchemy import Uuid, Column, Integer, String, DateTime, ForeignKey, relationship
from sqlalchemy.orm import declarative_base 

import uuid
from uuid6 import uuid7 

Base = declarative_base()


class UploadSession(Base):
    __tablename__ = "uploads_sessions"

    upload_id = Column(Uuid, primary_key=True, default=uuid7),
    user_id = Column(Integer, ForeignKey("fsm_users.user_id"), nullable=False)

    parent_tab = Column (String) # The name of parent table
    parent_id = Column(Uuid), # The id of parent registry
    tab_name = Column(String), # The table name (child table name)     
    col_name = Column(String), # The column name in table (child table)  
    
    content_type = Column(String),             
    total_size = Column(Integer),              
    total_chunks = Column(Integer),  
    received_chunks = Column(Integer),                            
    expires_at  = Column(DateTime),

    fsm_user = relationship("FSMUser", back_populates="uploads_sessions")

    # e.g, It could uploads 'photos', 'pdfs', 'videos' (children tables) for the each 'maintenances' (parent table). Or once child table 'files'  for all if qty is litle. In any case, the saving logic and the info registry creation could depends of child table or the file extension (the same thing?)...
    # Each file type ('child' table) could have fields id_'child', id_'parent', file_'child', url_'child' (The first two are mandatory)
    
    # complete_upload_service will explicitly read the values in both parent and child tables, then it will determine:
    # minio attributes (bucket (the most simply), file_name...) according to: parent_id, related model of parent_tab (how?), col_name
    # repo to be called (for writring into db the info of the saved (or uploaded) file in minio) according to: tab_name