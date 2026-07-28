from typing import Optional

from sqlalchemy.orm import Session

from app.models.master import Technician, Spare, Market, Equipment, Labsdl


def get_all_technicians(db: Session, page: int = 1, page_size: int = 50) -> list[Technician]:
    return _get_technician_query(db).offset(
        (page - 1) * page_size
    ).limit(page_size).all()


def get_technician_by_id(db: Session, technician_id: int) -> Optional[Technician]:
    return _get_technician_query(db).filter(
        Technician.technician_id == technician_id
    ).first()


def _get_technician_query(db: Session):
    return db.query(Technician)


def get_all_spares(db: Session, page: int = 1, page_size: int = 50) -> list[Spare]:
    return _get_spare_query(db).offset(
        (page - 1) * page_size
    ).limit(page_size).all()


def get_spare_by_id(db: Session, spare_id: int) -> Optional[Spare]:
    return _get_spare_query(db).filter(
        Spare.spare_id == spare_id
    ).first()


def _get_spare_query(db: Session):
    return db.query(Spare)


def get_all_markets(db: Session, page: int = 1, page_size: int = 50) -> list[Market]:
    return _get_market_query(db).offset(
        (page - 1) * page_size
    ).limit(page_size).all()


def get_market_by_id(db: Session, market_id: int) -> Optional[Market]:
    return _get_market_query(db).filter(
        Market.market_id == market_id
    ).first()


def _get_market_query(db: Session):
    return db.query(Market)


def get_all_equipment(db: Session, page: int = 1, page_size: int = 50) -> list[Equipment]:
    return _get_equipment_query(db).offset(
        (page - 1) * page_size
    ).limit(page_size).all()


def get_equipment_by_id(db: Session, equipment_id: int) -> Optional[Equipment]:
    return _get_equipment_query(db).filter(
        Equipment.equipment_id == equipment_id
    ).first()


def _get_equipment_query(db: Session):
    return db.query(Equipment)


def get_all_labsdls(db: Session, page: int = 1, page_size: int = 50) -> list[Labsdl]:
    return _get_labsdl_query(db).offset(
        (page - 1) * page_size
    ).limit(page_size).all()


def get_labsdl_by_id(db: Session, labsdl_id: int) -> Optional[Labsdl]:
    return _get_labsdl_query(db).filter(
        Labsdl.labsdl_id == labsdl_id
    ).first()


def _get_labsdl_query(db: Session):
    return db.query(Labsdl)
