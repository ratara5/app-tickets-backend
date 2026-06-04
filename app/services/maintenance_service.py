from types import SimpleNamespace
from pydantic import UUID7

from datetime import datetime, timedelta
import secrets, asyncio, io

from app.core.utils.dates import get_holidays
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.ticket import Ticket
from app.models.maintenance import Maintenance
from app.models.pause import Pause

from app.schemas.maintenance import MaintenanceUpdate
from app.schemas.ticket import TicketStatus
from app.schemas.pause import PauseRequest

from app.repositories.maintenance_repo import (create_maintenance, 
                                                save_maintenance, 
                                                get_visible_maintenances,
                                                get_maintenance_by_id,
                                                add_maintenance_spare,
                                                add_maintenance_technician)

from app.services.registry import service
from app.services.ticket_service import validate_transition
from app.services.pause_service import create_new_pause

from app.core.settings import settings
from app.core.storage import upload_file, get_presigned_url
from concurrent.futures import ThreadPoolExecutor


_executor = ThreadPoolExecutor()  # for synchronous operations in MinIO



def create_new_maintenance(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...

    maintenance = create_maintenance(db, data, current_user)
    
    # Lógica de negocio después de persistir
    # ...

    return maintenance

async def update_existing(maintenance_id: UUID7, 
                          payload: MaintenanceUpdate, 
                          current_user, 
                          db: Session, 
                          files: dict):
    maintenance = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    # Verify if associated ticket exists and its status is IN PROGRESS o PAUSED
    ticket = db.query(Ticket).filter(Ticket.ticket_id == maintenance.ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    if ticket.estado not in (TicketStatus.in_progress, TicketStatus.paused):
        raise HTTPException(
            422, f"No se puede crear maintenance: ticket en estado {ticket.estado}"
        )
    
    #################################################
    ##### Business logic before data persistance ####
    #################################################

    ### Upload maintenance file (in the table per se) ###
    for col_name, upload_file_obj in files.items():
        if upload_file_obj is None:
            continue
        content = await upload_file_obj.read()
        _, original_filename, full_object_path = build_object_path_maintenances(
            maintenance, col_name, upload_file_obj.content_type
        )
        result = await asyncio.get_event_loop().run_in_executor(
            _executor,
            lambda: upload_file(
                file_stream=io.BytesIO(content),
                original_filename=original_filename,
                content_type=upload_file_obj.content_type,
                full_object_path=full_object_path,
                job_id=str(maintenance_id),
            )
        )

    ### Get values of computed or derivate fields ###
    start_edition = datetime.now().strftime("%Y-%m-%d %H:%M:%S+00") # TODO: Inject TZ from environment and datetime.now()

    # laboral schedule #
    labsdl_id = 1 # default
    ticket_date = ticket.ticket_date
    if ticket_date.weekday() >= 5 or ticket_date in get_holidays(settings.country_company):
        labsdl_id = 3

    # next status #
    maintenance_id = maintenance.maintenance_id
    last_pause = db.query(Pause).filter(
        Pause.maintenance_id == maintenance_id
    ).order_by(Pause.created_at.desc()).first()

    if start_edition < last_pause.created_at:
        real_mark_as = "PAUSED"
    else:
        real_mark_as = "CLOSED"

    data = SimpleNamespace(**payload.model_dump(), 
                           start_edition=start_edition, # Is it necessary to have this field in table?
                           labsdl_id=labsdl_id, # Is it necessary to have this field in table?
                           real_mark_as=real_mark_as, # Is it necessary to have this field in table?
                           initial_photo_path=full_object_path
                           )
    
    ##################################################
    ###### Save maintenance change (persistance) #####
    ##################################################

    maintenance = save_maintenance(db, data, current_user)

    ##################################################
    ###### Business logic after data persistance #####
    ##################################################

    ### Persists spares, technicians, (photos is apart), etc. related to maintenance ###

    # Spares #
    for r in payload.spares:
        add_maintenance_spare(db, maintenance.id, r)
    # Technicians #
    for t in payload.technicians:
        add_maintenance_technician(db, maintenance.id, t)

    ### Finish ###
    if labsdl_id == 3:
        return maintenance # If wkd o hld, it's necessary fill additional info before changing the ticket status
    
    if real_mark_as == "PAUSED":
        ticket.status = TicketStatus.paused
    else:
        ticket.status = TicketStatus.closed

    return maintenance

    

def list_maintenances(db, current_user, page: int = 1, page_size: int = 50):
    maintenances_list = get_visible_maintenances(db, current_user, page, page_size)
    return list(map(_serialize_maintenance_item, maintenances_list))

def pause_ticket(maintenance_id: int, payload: PauseRequest,
                  current_user, db: Session):
    ticket = db.query(Maintenance).filter(Maintenance.maintenance_id == maintenance_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    
    validate_transition(ticket.status, TicketStatus.paused)

    data = SimpleNamespace(maintenance_id=maintenance_id, **payload.model_dump())
    ticket.status = TicketStatus.paused
    db.commit()
    create_new_pause(db, data, current_user)
    return ticket

def get_maintenance(db: Session, maintenance_id: int, current_user):
    maintenance = get_maintenance_by_id(db, maintenance_id, current_user)
    if not maintenance:
        raise HTTPException(404, "Maintenance not found")
    return _serialize_maintenance_item(maintenance)

# Helpers
@service(schema=Maintenance)
def build_object_path_maintenances(maintenance: Maintenance, col_name, content_type):

    maintenance_date = maintenance.maintenance_date
    mes = maintenance_date.strftime("%B")
    anio = maintenance_date.strftime("%Y")
    serial = secrets.token_hex(4)
    ext = settings.ext_by_type.get(content_type, "")

    original_filename = f"{maintenance.id}.{col_name}.{serial}.{ext}"
    full_object_path = f"{settings.base_object_path}/{anio}/{mes}/{maintenance.ticket_id}/{original_filename}"
    
    return serial, original_filename, full_object_path

def _sign(path: str | None) -> str | None:
    """Generate presigned URL from object path. None if no path."""
    if not path:
        return None
    return get_presigned_url(
        settings.minio_default_bucket, path, expires=timedelta(seconds=settings.presigned_ttl)
    )

def _serialize_maintenance_item(m: Maintenance) -> dict:
    initial_photo_url = _sign(m.initial_photo_path)
    pdf_url = _sign(m.work_order.pdf_path if m.work_order else None)
    photos = list(map(lambda p: {
                "photo_id": p.id, 
                "photo_url": _sign(p.photo_path)
            }, m.photos))
    
    spares=[{ # map or comprehension: are equivalent in terms of speed. But comprehension is more pythonic
        "spare_id": ms.spare.spare_id,
        "name": ms.spare.name,
        "price": ms.spare.price,
        "qty": ms.qty
        } for ms in m.spares],
    technicians=[{
        "technician_id": mt.technician.technician_id,
        "technician_name": mt.technician.fsm_user.user_name,
        "start_hour": mt.start_hour,
        "end_hour": mt.end_hour
    } for mt in m.technicians]
    
    return SimpleNamespace( **m.model_dump(), # The fields into maintenance table
                           
                            # The fields of related tables
                            ticket_date=m.ticket.ticket_date,
                            ticket_description=m.ticket.ticket_description,
                            ticket_status=m.ticket.status,

                            # The fields of related tables of related tables
                            market_name=m.ticket.market.market_name,
                            equipment_name=m.ticket.equipment.equipment_name,

                            # presigned URLs from minIO path fields
                            initial_photo_url=initial_photo_url,
                            pdf_url=pdf_url,
                            photos= photos,
                            
                            # fields of related tables
                            technicians=technicians,
                            spares=spares
                            )