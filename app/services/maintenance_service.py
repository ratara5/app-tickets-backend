from types import SimpleNamespace
from pydantic import UUID7
import structlog

from datetime import datetime, timedelta
import secrets, asyncio, io

from app.core.utils.dates import get_holidays
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.ticket import Ticket
from app.models.maintenance import Maintenance, Pause

from app.models.master import Technician

from app.schemas.user import CurrentUser, UserRole
from app.schemas.maintenance import MaintenanceUpdate
from app.schemas.ticket import TicketStatus
from app.schemas.pause import PauseRequest

import app.repositories.maintenance_repo as maintenance_repo
import app.repositories.ticket_repo as ticket_repo

from app.services.registry import service
import app.services.ticket_service as ticket_svc

from app.core.settings import settings
from app.core.storage import upload_file, delete_object, get_presigned_url
from concurrent.futures import ThreadPoolExecutor


_executor = ThreadPoolExecutor()  # for synchronous operations in MinIO
_log = structlog.get_logger()



def create_new_maintenance(db, data, current_user):
    # Lógica de negocio antes de persistir
    # ...

    maintenance = maintenance_repo.create_maintenance(db, data, current_user)

    # Lógica de negocio después de persistir
    # ...

    return _serialize_maintenance_item(maintenance)

def get_maintenance(db: Session, maintenance_id: UUID7, current_user):
    maintenance = maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)
    if not maintenance:
        raise HTTPException(404, "Maintenance not found")
    assert_ownership(maintenance, current_user, db)
    return _serialize_maintenance_item(maintenance)

def get_maintenance_by_ticket(db: Session, ticket_id: int, current_user):
    """Lookup the unique maintenance of a ticket (resume flow). 404 when absent."""
    maintenance = maintenance_repo.get_maintenance_by_ticket(db, ticket_id)
    if not maintenance:
        raise HTTPException(404, "Maintenance not found")
    assert_ownership(maintenance, current_user, db)
    return _serialize_maintenance_item(maintenance)

def list_maintenances(db, current_user, page: int = 1, page_size: int = 50):
    maintenances_list = maintenance_repo.get_visible_maintenances(db, current_user, page, page_size)
    return list(map(_serialize_maintenance_item, maintenances_list))

async def update_existing(db: Session, 
                          maintenance_id: UUID7, 
                          payload: MaintenanceUpdate, 
                          current_user, 
                          files: dict,
                          initial_photo_action: str = "keep"):
    maintenance = maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)
    if not maintenance:
        raise HTTPException(404, "Maintenance not found")
    assert_ownership(maintenance, current_user, db)

    if initial_photo_action not in ("keep", "replace", "clear"):
        raise HTTPException(422, "initial_photo_action must be keep, replace, or clear")

    initial_photo_file = files.get("initial_photo_file")
    if initial_photo_action == "clear" and initial_photo_file is not None:
        raise HTTPException(422, "initial_photo_file must be omitted when clearing the photo")
    if initial_photo_action == "replace" and initial_photo_file is None:
        raise HTTPException(422, "initial_photo_file is required when replacing the photo")

    old_photo_path = maintenance.initial_photo_path
    full_object_path = old_photo_path
    if initial_photo_action == "clear":
        full_object_path = None
    elif initial_photo_file is not None:
        initial_photo_action = "replace"

    # Verify if associated ticket exists and its status is IN PROGRESS o PAUSED
    ticket = ticket_repo.get_ticket_by_id(db, maintenance.ticket_id, current_user)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.status not in (TicketStatus.in_progress, TicketStatus.paused):
        raise HTTPException(
            422, f"It's not possible to create maintenance: ticket status {ticket.status}"
        )
    
    #################################################
    ##### Business logic before data persistance ####
    #################################################

    ### Upload maintenance file (in the table per se) ###
    for col_name, upload_file_obj in files.items():
        if upload_file_obj is None or initial_photo_action != "replace":
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

    ### Compute server-side fields ###
    ticket_date = ticket.ticket_date
    labsdl_id = 3 if (ticket_date.weekday() >= 5 or ticket_date in get_holidays(settings.country_company)) else 1

    # Spares # (idempotent replace, not append — see repo docs)
    maintenance_repo.replace_maintenance_spares(
        db, maintenance.maintenance_id, payload.spares, current_user
    )
    # Technicians #
    maintenance_repo.replace_maintenance_technicians(
        db, maintenance.maintenance_id, payload.technicians, current_user
    )
    # Pauses #
    maintenance_repo.replace_maintenance_pauses(
        db, maintenance.maintenance_id, payload.pauses, current_user
    )

    last_pause = (
        db.query(Pause)
        .filter(Pause.maintenance_id == maintenance.maintenance_id)
        .order_by(Pause.created_at.desc())
        .first()
    )
    real_mark_as = "PAUSED" if (maintenance.updated_at is None or (last_pause and last_pause.created_at > maintenance.updated_at)) else "CLOSED"
    _log.info(
        "maintenance_save_mark_as",
        maintenance_updated_at=maintenance.updated_at if maintenance.updated_at else "NULL in SQL",
        last_pause_created_at=last_pause.created_at if last_pause else None,
        real_mark_as=real_mark_as,
    )
    maintenance.labsdl_id = labsdl_id
    maintenance.initial_photo_path = full_object_path
    
    ##################################################
    ###### Save maintenance change (persistance) #####
    ##################################################

    maintenance = maintenance_repo.update_maintenance(db, maintenance, payload, current_user)

    if old_photo_path and old_photo_path != full_object_path:
        try:
            delete_object(old_photo_path)
        except Exception as error:
            _log.error(
                "maintenance_initial_photo_cleanup_failed",
                maintenance_id=str(maintenance_id),
                object_path=old_photo_path,
                error=str(error),
            )

    ##################################################
    ###### Business logic after data persistance #####
    ##################################################

    ### Persists spares, technicians, (photos is apart), etc. related to maintenance ###
    

    ### Finish ###
    if labsdl_id == 3:
        return maintenance # If wkd o hld, it's necessary fill additional info before changing the ticket status
    
    if real_mark_as == "PAUSED":
        status = TicketStatus.paused
    else:
        status = TicketStatus.closed
    
    ticket_repo.update_ticket_status(db, ticket, status, current_user)

    # Fresh, fully-loaded read of the replaced children before serialization —
    # avoids serving stale in-memory relationship collections.
    db.expire_all()
    maintenance = maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)
    return _serialize_maintenance_item(maintenance)


def delete_maintenance_photo(db: Session, maintenance_id: UUID7, photo_id: int, current_user):
    maintenance = maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)
    if not maintenance:
        raise HTTPException(404, "Maintenance not found")
    assert_ownership(maintenance, current_user, db)

    from app.repositories.photo_repo import get_photo, delete_photo

    photo = get_photo(db, maintenance_id, photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")

    photo_path = photo.photo_path
    if photo_path:
        try:
            delete_object(photo_path)
        except Exception as error:
            _log.error(
                "maintenance_photo_delete_object_failed",
                maintenance_id=str(maintenance_id),
                photo_id=photo_id,
                object_path=photo_path,
                error=str(error),
            )

    delete_photo(db, photo)

    db.expire_all()
    maintenance = maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)
    return _serialize_maintenance_item(maintenance)


def delete_maintenance(maintenance_id: UUID7, current_user, db: Session):
    maintenance = maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user) 
    if not maintenance:
        raise HTTPException(404, "Maintenance not found")
    return maintenance_repo.delete_maintenance_by_id(db, maintenance, current_user)


# Helpers
def assert_ownership(mnt: Maintenance, current_user: CurrentUser, db: Session):
    if current_user.user_role == UserRole.director:
        return
    technician = db.query(Technician).filter(Technician.user_id == current_user.user_id).first()
    if technician and mnt.ticket.assigned_to != technician.technician_id:
        raise HTTPException(403, "Forbidden")

@service(schema=Maintenance)
def build_object_path_maintenances(maintenance: Maintenance, col_name, content_type):

    maintenance_date = maintenance.maintenance_date
    mes = maintenance_date.strftime("%B")
    anio = maintenance_date.strftime("%Y")
    serial = secrets.token_hex(4)
    ext = settings.ext_by_type.get(content_type, "")

    original_filename = f"{maintenance.maintenance_id}.{col_name}.{serial}.{ext}"
    full_object_path = f"{settings.base_object_path}/{anio}/{mes}/{maintenance.ticket_id}/{original_filename}"
    
    return serial, original_filename, full_object_path

def _sign(path: str | None) -> str | None:
    """Generate presigned URL from object path. None if no path."""
    if not path:
        return None
    return get_presigned_url(
        path, expires_hours=settings.presigned_ttl
    )

def _serialize_maintenance_item(maintenance: Maintenance) -> dict:
    columns = {c.name: getattr(maintenance, c.name) for c in maintenance.__table__.columns}
    initial_photo_url = _sign(maintenance.initial_photo_path)
    pdf_url = _sign(maintenance.worksheet.pdf_path if maintenance.worksheet else None)
    photos = list(map(lambda p: {
                "photo_id": p.id, 
                "photo_url": _sign(p.photo_path)
            }, maintenance.photos))
    
    spares=[{ # map or comprehension: are equivalent in terms of speed. But comprehension is more pythonic
        "spare_id": ms.spare.spare_id,
        "name": ms.spare.spare_name,
        "price": ms.spare.price,
        "qty": ms.qty
        } for ms in maintenance.spares]
    technicians=[{
        "technician_id": mt.technician.technician_id,
        "technician_name": mt.technician.fsm_user.user_name,
        "start_hour": mt.start_hour,
        "end_hour": mt.end_hour
    } for mt in maintenance.technicians]
    pauses=[{
        "pause_reason": p.pause_reason,
        "created_at": p.created_at
    } for p in maintenance.pauses]
    
    return SimpleNamespace( **columns, # The fields into maintenance table

                            # presigned URLs from minIO path fields
                            initial_photo_url=initial_photo_url,
                            pdf_url=pdf_url,
                            photos=photos,
                            
                            # fields of related tables
                            technicians=technicians,
                            spares=spares,
                            pauses=pauses
                            )