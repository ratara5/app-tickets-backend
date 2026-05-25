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
    parent_tab = Column (String) # El nombre de la tabla padre
    parent_id = Column(Uuid), # El id de la tabla padre 
    tab_name = Column(String), # El nombre de la tabla     
    col_name = Column(String), # El nombre de la columna   
    user_email = Column(String), 
    content_type = Column(String),             
    total_size = Column(Integer),              
    total_chunks = Column(Integer),  
    received_chunks = Column(Integer),                            
    expires_at  = Column(DateTime)  

    # Por ejemplo, podrían subirse 'fotos', 'pdfs', 'videos' (tablas hijas) de usuarios (tabla padre). O una sola tabla hija 'archivos'  para todo si la cantidad es pequeña. En todo caso, la lógica de guardado y creación de registro de info podría depender de la tabla hija o de la extensión del archivo (lo mismo?)...
    # Y cada tipo de archivo (tabla 'hija') tener campos id_'hija', id_'padre', archivo_'hija', url_'hija' (los dos primeros obligatorios)
    
    # complete_upload_service leerá explícitamente los valores de las tablas parent e hija y determinará:
    # atributos minio (bucket (más sencillo), nombre del archivo...) según el: parent_id, modelo relacionado de parent_tab (cómo?), col_name
    # repo a llamar (para escritura en db de la info del archivo guardado en minio) según el: tab_name