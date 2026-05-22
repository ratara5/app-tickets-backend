from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

class RepuestoIn(BaseModel):
    id_mantenimiento: int
    id_repuesto: int
    cantidad: int

class TecnicoAdicionalIn(BaseModel):
    id_mantenimiento: int
    id_tecnico: int
    hora_entrada: datetime 
    hora_salida: datetime

class MantenimientoCreate(BaseModel):
    nro_ticket: int

class MantenimientoUpdate(BaseModel):
    nro_ticket: int # Se necesita para validar el ticket y su estado antes de permitir la actualización
    fecha_trabajo: Optional[date] = None # Se puede o no enviar, igual se asigna automáticamente al guardar si no se envía

    # Campos obligatorios para actualizar el mantenimiento existente
    descripcion_mantenimiento: str
    archivo_foto_inicio: str

    # Campos calculados o derivados (en el service)
    # inicio_mantenimiento: Optional[datetime] = None # O asignar automáticamente al guardar?
    # inicio_edicion: Optional[datetime] = None
    # tipo_jornada: Optional[int] = None 
    # real_marcar_como: Optional[str] = None

    # Campos técnicos (Columnas técnicas)
    carpeta_soporte: Optional[str] = None
    formato_soporte: Optional[str] = None
    url_foto_inicio: Optional[str] = None
    url_informe_soporte: Optional[str] = None
    
    # Hijas o partes de mantenimiento
    repuestos: Optional[List[RepuestoIn]] = []
    tecnicos_adicionales: Optional[List[TecnicoAdicionalIn]] = []
    foto_ids: Optional[List[int]] = []

    # Campos para la hoja de trabajo
    observaciones: Optional[str] = None
    nombre_recibe: Optional[str] = None
    cedula_recibe: Optional[str] = None
    cargo_recibe: Optional[str] = None
    sap_recibe: Optional[str] = None
    consecutivo_fus: Optional[str] = None
    firma_recibe: Optional[str] = None
    
