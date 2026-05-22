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
    nro_ticket: int
    fecha_trabajo: Optional[date] = None
    descripcion_mantenimiento: str
    tipo_jornada: Optional[int] = None
    carpeta_soporte: Optional[str] = None
    formato_soporte: Optional[str] = None
    archivo_foto_inicio: Optional[str] = None
    url_foto_inicio: Optional[str] = None
    url_informe_soporte: Optional[str] = None
    inicio_mantenimiento: Optional[datetime] = None
    real_marcar_como: Optional[str] = None
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
    inicio_edicion: Optional[datetime] = None
