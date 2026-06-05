from __future__ import annotations

from datetime import datetime
from pathlib import Path
from pydantic import UUID7
from types import SimpleNamespace

import base64
import io
import json

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

import app.repositories.worksheet_repo as ws_repo

from app.core.storage import upload_file, get_presigned_url
from app.core.settings import settings


# helpers
def _get_or_create_worksheet(db: Session, maintenance_id: UUID7, current_user) -> Worksheet:
    ws = ws_repo.get_worksheet_by_maintenance_id(db, maintenance_id, current_user)
    if not ws:
        ws_repo.create_worksheet(db, maintenance_id, current_user)
    return ws

def _number_sheet(maintenance_id: UUID7) -> str:
    year = datetime.now().year
    return f"WS-{year}-{maintenance_id:06d}"


def _build_context(maintenance_dto: Maintenance, ws: Worksheet, db:Session, current_user) -> dict:
    """
    Groups in a flat dict all the Jinja2 template needs.
    Equivalent to browse() + computed fields in Odoo
    """
    ticket_dto = ticket_svc.get_ticket(db=db, ticket_id=maintenance_dto.ticket_id, current_user=current_user)

    return {
        # Client info / form
        "client_company_name": settings.client_company_name,
        "client_format_name": settings.client_format_name,
        "client_format_code": 9999, # TODO: Field (not static) in worksheet

        # Contractor info / my company
        "contractor_name": settings.contractor_name,
        "contractor_nit": settings.contractor_nit,
        "contractor_contact": settings.contractor_contact,
        "contractor_phone": settings.contractor_phone,

        # Market
        "market_name": ticket_dto.market_name,
        "city": ticket_dto.city,
        "state": ticket_dto.state,

        # Date
        "maintenance_date": maintenance_dto.maintenance_date,

        # Equipment
        "equipment_name": ticket_dto.equipment_name,

        # Ticket Description
        "ticket_description": ticket_dto.ticket_description,

        # Maintenance Description
        "maintenance_description": maintenance_dto.maintenance_description,

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
def upsert_worksheet(db: Session, maintenance_id: int, data: WorksheetUpsert, current_user) -> Worksheet:
    """Creates or updates the fields that the technician fills in field."""
    ws = _get_or_create_worksheet(db, maintenance_id, current_user)

    if ws.closed:
        raise HTTPException(409, "The sheet is already closed and cannot be modified.")
    
    ws_repo.update_existing_ws(db, data, current_user)
    return ws

def generate_pdf(maintenance_id: int, db: Session, current_user) -> tuple[Worksheet, str]:
    """
    Render the PDF, upload it to MinIO and close the sheet.
    Returns (worksheet, presigned_url).
    """ 
    ws = _get_or_create_worksheet(db=db, maintenance_id=maintenance_id, current_user=current_user)

    if ws.closed:
        # Already generated: we return a fresh URL without regenerating
        url = get_presigned_url(ws.pdf_path, 1)
        return ws, url
    
    # Render
    env = Environment(loader=FileSystemLoader(str(settings.template_dir)))
    template = env.get_template("worksheet.html")
    maintenance_dto = maintenance_svc.get_maintenance(db, maintenance_id, current_user)
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

    ws = ws_repo.save_worksheet(db, ws, full_object_path, number)

    url = get_presigned_url(ws.pdf_path, 1)

    return ws, url