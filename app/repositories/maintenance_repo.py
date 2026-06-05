import datetime
from typing import List

from sqlalchemy import or_, and_, joinedload, selectinload
from sqlalchemy.orm import Session

from app.core.utils.dates import start_of_month

from app.models.ticket import Ticket
from app.models.maintenance import Maintenance, MaintenanceSpare, MaintenanceTechnician
from app.models.master import Technician

from app.schemas.ticket import TicketStatus
from app.schemas.user import UserRole


def create_maintenance(db, data, current_user):
    maintenance = Maintenance(
        ticket_id=data.ticket_id,
        maintenance_date=data.maintenance_date or datetime.now().strftime("%d/%m/%Y") # TODO: To inject TZ from environment and apply .strftime("%d/%m/%Y")
        # created_by=current_user.user_id # It's not necessary overwrite auditmixin
    )

    db.add(maintenance)
    db.flush()
    db.refresh(maintenance)

    return maintenance

def save_maintenance(db, data, current_user):
    maintenance = Maintenance(
        ticket_id=data.ticket_id,
        maintenance_description=data.maintenance_description,
        # maintenance_start=data.maintenance_start, # equals to created_at # TODO: To inject TZ from environment
        initial_photo_path=data.initial_photo_path,
        labsdl_id=data.labsdl_id,
        edition_start=datetime.now().strftime("%Y-%m-%d %H:%M:%S+00"), # TODO: To inject TZ from environment and apply .strftime("%Y-%m-%d %H:%M:%S+00")

        # carpeta_soporte=data.carpeta_soporte,
        # formato_soporte=data.formato_soporte,
        # url_foto_inicio=data.url_foto_inicio,
        # url_informe_soporte=data.url_informe_soporte,

        # created_by=current_user.user_id # It's not necessary overwrite auditmixin
    )
    db.add(maintenance)
    db.flush()  # get ID without do commit

    return maintenance

def get_visible_maintenances(db, 
                             current_user, 
                             page: int = 1, 
                             page_size: int = 50) -> List[Maintenance]:
    query = _get_query(db, current_user)

    if current_user.user_role == UserRole.technician:
        query = query.filter(
            and_(
                or_(
                    Ticket.assigned_to == None,
                    Ticket.assigned_to == current_user.technician.technician_id
                ),
                Ticket.status != TicketStatus.cancelled
            )
        )
    
    return (
        query
        .order_by(Ticket.ticket_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

def get_maintenance_by_id( # The client side cache eliminates 90% calls to this endpoint.
    db: Session, 
    maintenance_id: int, 
    current_user
) -> Maintenance | None:   
    query = _get_query(db, current_user)
    query.filter(Maintenance.id_maintenance == maintenance_id)
    # The Logic for filter by user_role now is a validation in maintenance_service

    return query.first()

def add_maintenance_spare(db, maintenance_id, r):
    db.add(MaintenanceSpare(
        maintenance_id=maintenance_id,
        spare_id=r.spare_id,
        qty=r.qty
    ))

def add_maintenance_technician(db, maintenance_id, t):
    db.add(MaintenanceTechnician(
        maintenance_id_id=maintenance_id,
        technician_id=t.technician_id,
        start_hour=t.start_hour,
        end_hour=t.end_hour
    ))

# avoid N+1 problem, is better than relationship access with dot notation (out of repo)
def _get_query(db, current_user):
    limit_date = start_of_month(-2)

    query = (
        db.query(Maintenance)
        .join(Maintenance.ticket)
        .options(
            joinedload(Maintenance.ticket)
                .joinedload(Ticket.market)
                .joinedload(Ticket.equipment)
                .joinedload(Ticket.cancellation),
            joinedload(Maintenance.worksheet),
            selectinload(Maintenance.photos),
            selectinload(Maintenance.technicians)
                .joinedload(MaintenanceTechnician.technician)
                .joinedload(Technician.fsm_user),
            selectinload(Maintenance.spares)
                .joinedload(MaintenanceSpare.spare),
            selectinload(Maintenance.pauses) 
        )
        .filter(
            Ticket.ticket_date >= limit_date
        )
    )

    return query

def delete_maintenance_by_id(db, maintenance, current_user):

    db.delete(maintenance)
    db.commit()
   
    return maintenance.maintenance_id