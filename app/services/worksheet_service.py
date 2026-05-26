from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

from pydantic import UUID7

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import Session
from weasyprint import HTML

from models.worksheet import Worksheet
from models.mantenimiento import *
from models.ticket import Ticket
from models.master import *

from schemas.worksheet import WorksheetUpsert

from core.storage import upload_file, get_presigned_url


# helpers

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "reports"

def _get_or_create_worksheet(id_mantenimiento: UUID7, db: Session) -> Worksheet:
    ws = db.query(Worksheet).filter_by(id_mantenimiento=id_mantenimiento).first()
    if not ws:
        ws = Worksheet(id_mantenimiento=id_mantenimiento)
        db.add(ws)
        db.flush()
    return ws

def _number_sheet(id_mantenimiento: UUID7) -> str:
    year = datetime.now().year
    return f"WS-{year}-{id_mantenimiento:06d}"

def _build_context(mtto: Mantenimiento, ws: Worksheet, db:Session) -> dict:
    """
    Reúne en un dict plano todo lo que la plantilla Jinja2 necesita.
    Equivale al browse() + computed fields de Odoo
    """
    ticket = db.query(Ticket).filter(nro_ticket=mtto.nro_ticket).first()
    tienda =  db.query(Tienda).filter(nro_tienda=ticket.nro_tienda).first()
    equipo = db.query(Equipo).filter(nro_equipo=ticket.nro_equipo).first()
    tecnicos = ( # mtto.tecnicos # relación M2M
        db.query(
            Tecnico.nombre,
            MantenimientoTecnico.hora_entrada,
            MantenimientoTecnico.hora_salida
        )
        .join(
            Tecnico,
            MantenimientoTecnico.id_tecnico == Tecnico.id_tecnico
        )
        .filter(
            MantenimientoTecnico.id_mantenimiento == mtto.id_mantenimiento
        )
        .all()
    ) 
    repuestos = ( # mtto.repuestos # relación M2M (?)
        db.query(
            Repuesto.nombre,
            MantenimientoRepuesto.cantidad,
            Repuesto.unidades
        )
        .join(
            Repuesto,
            MantenimientoRepuesto.id_repuesto == Repuesto.id_repuesto
        )
        .filter(
            MantenimientoRepuesto.id_mantenimiento == mtto.id_mantenimiento
        )
        .all()
    )

    return {
        # Datos cliente / formato
        "client_company_name": getattr(ticket, "client_company_name", "CLIENT_COMPANY_NAME"),
        "client_format_name": getattr(ticket, "client_format_name", "CLIENT_FORMAT_NAME"),
        "client_format_code": getattr(ticket, "client_format_code", "CLIENT_FORMAT_CODE"),

        # Datos contratista / mi empresa
        "contractor_name": getattr(mtto, "contractor_name", "CONTRACTOR_NAME"),
        "contractor_nit": getattr(mtto, "contractor_nit", "CONTRACTOR_NIT"),
        "contractor_contact": getattr(mtto, "contractor_contact", "CONTRACTOR_CONTACT"),
        "contractor_phone": getattr(mtto, "contractor_phone", "CONTRACTOR_PHONE"),

        # Tienda
        "nombre_tienda": getattr(tienda, "nombre_tienda", "NOMBRE_TIENDA"),
        "ciudad": getattr(tienda, "ciudad", "CIUDAD"),
        "departamento": getattr(tienda, "departamento", "DEPARTAMENTO"),

        # Fecha
        "fecha_trabajo": getattr(mtto, "fecha_trabajo", "1/11/1111"),

        # Equipo
        "nombre_equipo": getattr(equipo, "nombre_equipo", "NOMBRE_EQUIPO"),

        # Descripción Ticket
        "descripcion_ticket": getattr(ticket, "descripcion_ticket", "DESCRIPCION_TICKET"),

        # Descripción Mantenimiento
        "descripcion_mantenimiento": getattr(mtto, "descripcion_mantenimiento", "DESCRIPCION_MANTENIMIENTO"),

        # Técnicos
        "tecnicos": [
            {"nombre": t.nombre, "hora_entrada": t.hora_entrada, "hora_salida": t.hora_salida}
            for t in tecnicos
        ], 

        # Repuestos
        "repuestos": [
            {"nombre": r.nombre, "cantidad": r.cantidad, "unidades": r.unidades}
            for r in repuestos
        ],

        # Datos del receptor (diligenciados en campo (?))
        "receiver_name": ws.receiver_name or "",
        "receiver_doc_id": ws.receiver_doc_id or "",        
        "receiver_position": ws.receiver_position or "",
        "receiver_sap": ws.receiver_sap or "",
        "receiver_signature": ws.receiver_signature or None,
        "receiver_signature_date": ws.receiver_signature_date,

        # Número de hoja
        "number_sheet": ws.sheet_number or _number_sheet(mtto.id_mantenimiento),
        "generation_date": datetime.now()
    }

# Casos de uso
def upsert_worksheet(id_mantenimiento: int, data: WorksheetUpsert, db: Session) -> Worksheet:
    """Crea o actualiza los campos que el tecnico llena en campo."""
    ws = _get_or_create_worksheet(id_mantenimiento, db)

    if ws.closed:
        raise HTTPException(409, "La hoja ya fue cerrada y no puede modificarse.")
    
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ws, field, value)
    
    ws.updated_at = datetime.now()
    db.commit()
    db.refresh(ws)
    return ws

def generate_pdf(id_mantenimiento: int, db: Session) -> tuple[Worksheet, str]:
    """
    Renderiza el PDF, lo sube a MinIO y cierra la hoja.
    Retorna (worksheet, presigned_url).
    """
    mtto = db.query(Mantenimiento).filter(id_mantenimiento=id_mantenimiento).first()
    if not mtto:
        raise HTTPException(404, "Mantenimiento no encontrado.")
    
    ws = _get_or_create_worksheet(id_mantenimiento, db)

    if ws.closed:
        # Ya generado: devolvemos URL fresca sin regenerar
        url = get_presigned_url(ws.pdf_url, 1)
        return ws, url
    
    # Renderizar
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("worksheet.html")
    ctx = _build_context(mtto, ws)
    html_str = template.render(**ctx)

    # PDF en memoria
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()

    # Subir a minio
    fecha_trabajo = mtto.fecha_trabajo
    mes = fecha_trabajo.strftime("%B")
    anio = fecha_trabajo.strftime("%Y")

    original_filename = f"Soporte_{mtto.nro_ticket}.pdf"
    full_object_path = f"Mantenimiento/Correctivos/{anio}/{mes}/{mtto.nro_ticket}/{original_filename}"

    upload_file(file_stream=io.BytesIO(pdf_bytes), 
            original_filename=original_filename,
            content_type="application/pdf",
            full_object_path=full_object_path,
            job_id=id_mantenimiento)
    
    # Close sheet
    number = _number_sheet(id_mantenimiento)
    ws.sheet_number = number
    ws.pdf_url = full_object_path #En la DB se guarda el path (Mantenimiento/Correctivos/2025/Mayo/.../Soporte_....pdf) y cada vez que se necesita servirlo se genera una URL presignada fresca en ese momento.
    ws.generated_at = datetime.now()
    ws.closed = 1
    db.commit()
    db.refresh(ws)