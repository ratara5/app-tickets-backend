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

from app.schemas.worksheet import WorksheetUpsert

import app.services.ticket_service as ticket_svc
import app.services.maintenance_service as maintenance_svc

from app.core.storage import upload_file, get_presigned_url
from app.core.settings import settings


# helpers
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

def _build_context(maintenance_dto: Maintenance, ws: Worksheet, db:Session) -> dict:
    """
    Groups in a flat dict all the Jinja2 template needs.
    Equivalent to browse() + computed fields in Odoo
    """
    ticket_dto = ticket_svc.get_ticket()

    # market =  db.query(Market).filter(market_id=ticket.market_id).first()
    # equipo = db.query(Equipment).filter(equipment_id=ticket.equipment_id).first()
    # technicians = ( # maintenance.technicians # M2M relationship
    #     db.query(
    #         Technician.user_id,
    #         MaintenanceTechnician.start_hour,
    #         MaintenanceTechnician.end_hour
    #     )
    #     .join(
    #         Technician,
    #         MaintenanceTechnician.technician_id == Technician.technician_id
    #     )
    #     .filter(
    #         MaintenanceTechnician.maintenance_id == maintenance.maintenance_id
    #     )
    #     .all()
    # ) 
    # spares = ( # maintenance.spares # M2M relationship (?)
    #     db.query(
    #         Spare.spare_name,
    #         MaintenanceSpare.qty,
    #         Spare.unit
    #     )
    #     .join(
    #         Spare,
    #         MaintenanceSpare.spare_id == Spare.spare_id
    #     )
    #     .filter(
    #         MaintenanceSpare.maintenance_id == maintenance.maintenance_id
    #     )
    #     .all()
    # )

    return {
        # Client info / form
        "client_company_name": getattr(ticket_dto, "client_company_name", "CLIENT_COMPANY_NAME"),
        "client_format_name": getattr(ticket_dto, "client_format_name", "CLIENT_FORMAT_NAME"),
        "client_format_code": getattr(ticket_dto, "client_format_code", "CLIENT_FORMAT_CODE"),

        # Contractor info / my company
        "contractor_name": getattr(maintenance_dto, "contractor_name", "CONTRACTOR_NAME"),
        "contractor_nit": getattr(maintenance_dto, "contractor_nit", "CONTRACTOR_NIT"),
        "contractor_contact": getattr(maintenance_dto, "contractor_contact", "CONTRACTOR_CONTACT"),
        "contractor_phone": getattr(maintenance_dto, "contractor_phone", "CONTRACTOR_PHONE"),

        # Market
        "market_name": getattr(ticket_dto, "market_name", "NOMBRE_TIENDA"),
        "city": getattr(ticket_dto, "city", "CIUDAD"),
        "state": getattr(ticket_dto, "state", "DEPARTAMENTO"),

        # Date
        "maintenance_date": getattr(maintenance_dto, "maintenance_date", "1/11/1111"),

        # Equipment
        "equipment_name": getattr(ticket_dto, "equipment_name", "NOMBRE_EQUIPO"),

        # Ticket Description
        "ticket_description": getattr(ticket_dto, "ticket_description", "DESCRIPCION_TICKET"),

        # Maintenance Description
        "maintenance_description": getattr(maintenance_dto, "maintenance_description", "DESCRIPCION_MANTENIMIENTO"),

        # Technicians
        "technicians": [
            {"technician_name": mt.technician_name, "start_hour": mt.start_hour, "end_hour": mt.end_hour}
            for mt in maintenance_dto.technicians
        ], 

        # Spares
        "spares": [
            {"spare_name": ms.spare_name, "qty": ms.qty, "unit": ms.unit}
            for ms in maintenance_dto.spares
        ],

        # Receiver info (fill in field (?))
        "receiver_name": ws.receiver_name or "",
        "receiver_doc_id": ws.receiver_doc_id or "",        
        "receiver_position": ws.receiver_position or "",
        "receiver_sap": ws.receiver_sap or "",
        "receiver_signature": ws.receiver_signature or None,
        "receiver_signature_date": ws.receiver_signature_date,

        # Number sheet
        "number_sheet": ws.sheet_number or _number_sheet(maintenance_dto.maintenance_id),
        "generation_date": datetime.now()
    }

# Use cases
def upsert_worksheet(maintenance_id: int, data: WorksheetUpsert, db: Session) -> Worksheet:
    """Creates or updates the fields that the technician fills in field."""
    ws = _get_or_create_worksheet(maintenance_id, db)

    if ws.closed:
        raise HTTPException(409, "The sheet is already closed and cannot be modified.")
    
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ws, field, value)
    
    ws.updated_at = datetime.now()
    db.commit()
    db.refresh(ws)
    return ws

def generate_pdf(maintenance_id: int, db: Session) -> tuple[Worksheet, str]:
    """
    Render the PDF, upload it to MinIO and close the sheet.
    Returns (worksheet, presigned_url).
    """
    maintenance_dto = maintenance_svc.get_maintenance()
    
    ws = _get_or_create_worksheet(maintenance_id, db)

    if ws.closed:
        # Already generated: we return a fresh URL without regenerating
        url = get_presigned_url(ws.pdf_url, 1)
        return ws, url
    
    # Render
    env = Environment(loader=FileSystemLoader(str(settings.template_dir)))
    template = env.get_template("worksheet.html")
    ctx = _build_context(maintenance_dto, ws)
    html_str = template.render(**ctx)

    # PDF in memory
    pdf_bytes = HTML(string=html_str, base_url=str(settings.template_dir)).write_pdf()

    # Upload to MinIO
    fecha_trabajo = maintenance_dto.fecha_trabajo
    mes = fecha_trabajo.strftime("%B")
    anio = fecha_trabajo.strftime("%Y")

    original_filename = f"{settings.pdf_suffix}{maintenance_dto.ticket_id}.pdf"
    full_object_path = f"{settings.base_object_path}/{anio}/{mes}/{maintenance_dto.ticket_id}/{original_filename}"

    upload_file(file_stream=io.BytesIO(pdf_bytes), 
            original_filename=original_filename,
            content_type="application/pdf",
            full_object_path=full_object_path,
            job_id=maintenance_id)
    
    # Close sheet
    number = _number_sheet(maintenance_id)
    ws.sheet_number = number
    ws.pdf_path = full_object_path # In the db is saved the path (Mantenimiento/Correctivos/2025/Mayo/.../Soporte_....pdf) y cada vez que se necesita servirlo se genera una URL presignada fresca en ese momento.
    ws.generated_at = datetime.now()
    ws.closed = True
    db.commit()
    db.refresh(ws)