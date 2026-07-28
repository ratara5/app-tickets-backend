from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import app.repositories.master_repo as master_repo


def list_technicians(db: Session, page: int = 1, page_size: int = 50):
    return master_repo.get_all_technicians(db, page, page_size)


def get_technician(db: Session, technician_id: int):
    technician = master_repo.get_technician_by_id(db, technician_id)
    if not technician:
        raise HTTPException(404, "Technician not found")
    return technician


def list_spares(db: Session, page: int = 1, page_size: int = 50):
    return master_repo.get_all_spares(db, page, page_size)


def get_spare(db: Session, spare_id: int):
    spare = master_repo.get_spare_by_id(db, spare_id)
    if not spare:
        raise HTTPException(404, "Spare not found")
    return spare


def list_markets(db: Session, page: int = 1, page_size: int = 50):
    return master_repo.get_all_markets(db, page, page_size)


def get_market(db: Session, market_id: int):
    market = master_repo.get_market_by_id(db, market_id)
    if not market:
        raise HTTPException(404, "Market not found")
    return market


def list_equipment(db: Session, page: int = 1, page_size: int = 50):
    return master_repo.get_all_equipment(db, page, page_size)


def get_equipment_by_id(db: Session, equipment_id: int):
    equipment = master_repo.get_equipment_by_id(db, equipment_id)
    if not equipment:
        raise HTTPException(404, "Equipment not found")
    return equipment


def list_labsdls(db: Session, page: int = 1, page_size: int = 50):
    return master_repo.get_all_labsdls(db, page, page_size)


def get_labsdl(db: Session, labsdl_id: int):
    labsdl = master_repo.get_labsdl_by_id(db, labsdl_id)
    if not labsdl:
        raise HTTPException(404, "Labsdl not found")
    return labsdl
