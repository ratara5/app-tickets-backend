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

from app.models.worksheet import Worksheet
from app.models.maintenance import *
from app.models.ticket import Ticket
from app.models.master import *

from schemas.worksheet import WorksheetUpsert

from core.storage import upload_file, get_presigned_url


# helpers
TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "reports"

def _get_or_create_worksheet(maintenance_id: UUID7, db: Session) -> Worksheet:
    ws = db.query(Worksheet).filter_by(maintenance_id=maintenance_id).first()
    if not ws:
        ws = Worksheet(maintenance_id=maintenance_id)
        db.add(ws)
        db.flush()
    return ws

def _number_sheet(maintenance_id: UUID7) -> str:
    year = datetime.now().year
    return f"WS-{year}-{maintenance_id:06d}"

def _build_context(maintenance: Maintenance, ws: Worksheet, db:Session) -> dict:
    """
    Reúne en un dict plano todo lo que la plantilla Jinja2 necesita.
    Equivale al browse() + computed fields de Odoo
    """
    ticket = db.query(Ticket).filter(ticket_id=maintenance.ticket_id).first()
    market =  db.query(Market).filter(market_id=ticket.market_id).first()
    equipo = db.query(Equipment).filter(equipment_id=ticket.equipment_id).first()
    technicians = ( # maintenance.technicians # relación M2M
        db.query(
            Technician.user_id,
            MaintenanceTechnician.start_hour,
            MaintenanceTechnician.end_hour
        )
        .join(
            Technician,
            MaintenanceTechnician.technician_id == Technician.technician_id
        )
        .filter(
            MaintenanceTechnician.maintenance_id == maintenance.maintenance_id
        )
        .all()
    ) 
    spares = ( # maintenance.spares # relación M2M (?)
        db.query(
            Spare.spare_name,
            MaintenanceSpare.qty,
            Spare.unit
        )
        .join(
            Spare,
            MaintenanceSpare.spare_id == Spare.spare_id
        )
        .filter(
            MaintenanceSpare.maintenance_id == maintenance.maintenance_id
        )
        .all()
    )

    return {
        # CLient info / form
        "client_company_name": getattr(ticket, "client_company_name", "CLIENT_COMPANY_NAME"),
        "client_format_name": getattr(ticket, "client_format_name", "CLIENT_FORMAT_NAME"),
        "client_format_code": getattr(ticket, "client_format_code", "CLIENT_FORMAT_CODE"),

        # Contractor info / my company
        "contractor_name": getattr(maintenance, "contractor_name", "CONTRACTOR_NAME"),
        "contractor_nit": getattr(maintenance, "contractor_nit", "CONTRACTOR_NIT"),
        "contractor_contact": getattr(maintenance, "contractor_contact", "CONTRACTOR_CONTACT"),
        "contractor_phone": getattr(maintenance, "contractor_phone", "CONTRACTOR_PHONE"),

        # Market
        "market_name": getattr(market, "market_name", "NOMBRE_TIENDA"),
        "city": getattr(market, "city", "CIUDAD"),
        "state": getattr(market, "state", "DEPARTAMENTO"),

        # Date
        "maintenance_date": getattr(maintenance, "maintenance_date", "1/11/1111"),

        # Equipment
        "equipment_name": getattr(equipo, "equipment_name", "NOMBRE_EQUIPO"),

        # Ticket Description
        "ticket_description": getattr(ticket, "ticket_description", "DESCRIPCION_TICKET"),

        # Maintenance Description
        "maintenance_description": getattr(maintenance, "maintenance_description", "DESCRIPCION_MANTENIMIENTO"),

        # Technicians
        "technicians": [
            {"user_id": t.user_id, "start_hour": t.start_hour, "end_hour": t.end_hour}
            for t in technicians
        ], 

        # Spares
        "spares": [
            {"spare_name": r.spare_name, "qty": r.qty, "unit": r.unit}
            for r in spares
        ],

        # Receiver info (fill in field (?))
        "receiver_name": ws.receiver_name or "",
        "receiver_doc_id": ws.receiver_doc_id or "",        
        "receiver_position": ws.receiver_position or "",
        "receiver_sap": ws.receiver_sap or "",
        "receiver_signature": ws.receiver_signature or None,
        "receiver_signature_date": ws.receiver_signature_date,

        # Number sheet
        "number_sheet": ws.sheet_number or _number_sheet(maintenance.maintenance_id),
        "generation_date": datetime.now()
    }

# Use cases
def upsert_worksheet(maintenance_id: int, data: WorksheetUpsert, db: Session) -> Worksheet:
    """Crea o actualiza los campos que el tecnico llena en campo."""
    ws = _get_or_create_worksheet(maintenance_id, db)

    if ws.closed:
        raise HTTPException(409, "La hoja ya fue cerrada y no puede modificarse.")
    
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ws, field, value)
    
    ws.updated_at = datetime.now()
    db.commit()
    db.refresh(ws)
    return ws

def generate_pdf(maintenance_id: int, db: Session) -> tuple[Worksheet, str]:
    """
    Renderiza el PDF, lo sube a MinIO y cierra la hoja.
    Retorna (worksheet, presigned_url).
    """
    maintenance = db.query(Maintenance).filter(maintenance_id=maintenance_id).first()
    if not maintenance:
        raise HTTPException(404, "Maintenance no encontrado.")
    
    ws = _get_or_create_worksheet(maintenance_id, db)

    if ws.closed:
        # Ya generado: devolvemos URL fresca sin regenerar
        url = get_presigned_url(ws.pdf_url, 1)
        return ws, url
    
    # Renderizar
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("worksheet.html")
    ctx = _build_context(maintenance, ws)
    html_str = template.render(**ctx)

    # PDF en memoria
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()

    # Subir a minio
    fecha_trabajo = maintenance.fecha_trabajo
    mes = fecha_trabajo.strftime("%B")
    anio = fecha_trabajo.strftime("%Y")

    original_filename = f"Soporte_{maintenance.ticket_id}.pdf"
    full_object_path = f"Mantenimiento/Correctivos/{anio}/{mes}/{maintenance.ticket_id}/{original_filename}"

    upload_file(file_stream=io.BytesIO(pdf_bytes), 
            original_filename=original_filename,
            content_type="application/pdf",
            full_object_path=full_object_path,
            job_id=maintenance_id)
    
    # Close sheet
    number = _number_sheet(maintenance_id)
    ws.sheet_number = number
    ws.pdf_url = full_object_path #En la DB se guarda el path (Mantenimiento/Correctivos/2025/Mayo/.../Soporte_....pdf) y cada vez que se necesita servirlo se genera una URL presignada fresca en ese momento.
    ws.generated_at = datetime.now()
    ws.closed = 1
    db.commit()
    db.refresh(ws)