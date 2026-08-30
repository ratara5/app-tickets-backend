from datetime import datetime
from typing import List
from pydantic import UUID7

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.utils.dates import start_of_month

from app.models.ticket import Ticket
from app.models.maintenance import Maintenance, MaintenanceSpare, MaintenanceTechnician, Pause
from app.models.master import Technician

from app.schemas.ticket import TicketStatus
from app.schemas.user import UserRole


def create_maintenance(db, data, current_user, commit: bool = True):
    maintenance_date = data.maintenance_date
    if maintenance_date is None:
        maintenance_date = datetime.now()
    elif isinstance(maintenance_date, str):
        maintenance_date = datetime.fromisoformat(maintenance_date)

    maintenance = Maintenance(
        ticket_id=data.ticket_id,
        maintenance_date=maintenance_date,
        created_by=current_user.user_id,
        updated_by=current_user.user_id,
    )

    db.add(maintenance)
    if commit:
        # Legacy path (POST /maintenances): own transaction.
        db.commit()
    else:
        # Transactional start path: the caller owns the commit so the
        # ticket status transition and this insert commit atomically.
        db.flush()
    db.refresh(maintenance)

    return maintenance

def get_maintenance_by_ticket(db: Session, ticket_id: int) -> Maintenance | None:
    """Return the unique maintenance associated with a ticket, if any.

    Used by the idempotent start flow and the by-ticket lookup endpoint.
    No date filter: a maintenance may be older than the list window.
    """
    return (
        db.query(Maintenance)
        .options(
            joinedload(Maintenance.ticket).joinedload(Ticket.market),
            joinedload(Maintenance.ticket).joinedload(Ticket.equipment),
            joinedload(Maintenance.ticket).joinedload(Ticket.cancellation),
            joinedload(Maintenance.worksheet),
            selectinload(Maintenance.photos),
            selectinload(Maintenance.technicians)
                .joinedload(MaintenanceTechnician.technician)
                .joinedload(Technician.fsm_user),
            selectinload(Maintenance.spares)
                .joinedload(MaintenanceSpare.spare),
            selectinload(Maintenance.pauses)
        )
        .filter(Maintenance.ticket_id == ticket_id)
        .first()
    )

def update_maintenance(db, maintenance, data, current_user):
    for field, value in data.model_dump(exclude_none=True, exclude={"spares", "technicians", "pauses"}).items():
        setattr(maintenance, field, value)

    db.commit()
    db.refresh(maintenance)

    return maintenance

def _get_technician_id(db: Session, current_user) -> int | None:
    technician = db.query(Technician).filter(Technician.user_id == current_user.user_id).first()
    return technician.technician_id if technician else None


def get_visible_maintenances(db, 
                             current_user, 
                             page: int = 1, 
                             page_size: int = 50) -> List[Maintenance]:
    query = _get_query(db, current_user)

    if current_user.user_role == UserRole.technician:
        technician_id = _get_technician_id(db, current_user)
        query = query.filter(
            and_(
                or_(
                    Ticket.assigned_to == None,
                    Ticket.assigned_to == technician_id
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
    maintenance_id: UUID7, 
    current_user
) -> Maintenance | None:   
    query = _get_query(db, current_user)
    query = query.filter(Maintenance.maintenance_id == maintenance_id)
    # The Logic for filter by user_role now is a validation in maintenance_service

    return query.first()

def add_maintenance_spare(db, maintenance_id, r):
    db.add(MaintenanceSpare(
        maintenance_id=maintenance_id,
        spare_id=r.spare_id,
        qty=r.qty
    ))
    db.commit()

def add_maintenance_technician(db, maintenance_id, t):
    db.add(MaintenanceTechnician(
        maintenance_id=maintenance_id,
        technician_id=t.technician_id,
        start_hour=t.start_hour,
        end_hour=t.end_hour
    ))
    db.commit()

def add_pause(db, maintenance_id, p):
    db.add(Pause(
        maintenance_id=maintenance_id,
        pause_reason=p.pause_reason,
        created_at=p.created_at
    ))
    db.commit()


# avoid N+1 problem, is better than relationship access with dot notation (out of repo)
def _get_query(db, current_user):
    limit_date = start_of_month(-2)

    query = (
        db.query(Maintenance)
        .join(Maintenance.ticket)
        .options(
            joinedload(Maintenance.ticket).joinedload(Ticket.market),
            joinedload(Maintenance.ticket).joinedload(Ticket.equipment),
            joinedload(Maintenance.ticket).joinedload(Ticket.cancellation),
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
    ticket = db.query(Maintenance).join(Maintenance.ticket)
    db.delete(maintenance)
    db.commit()
   
    return ticket.ticket_id