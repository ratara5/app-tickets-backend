from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db

from app.schemas.master import (
    TechnicianResponse,
    SpareResponse,
    MarketResponse,
    EquipmentResponse,
    LabsdlResponse,
)

from app.services.master_service import *


router = APIRouter(prefix="")


@router.get("/technicians", response_model=list[TechnicianResponse])
def get_technicians(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return list_technicians(db, page, page_size)


@router.get("/technicians/{technician_id}", response_model=TechnicianResponse)
def get_technician_by_id(
    technician_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_technician(db, technician_id)


@router.get("/spares", response_model=list[SpareResponse])
def get_spares(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return list_spares(db, page, page_size)


@router.get("/spares/{spare_id}", response_model=SpareResponse)
def get_spare_by_id(
    spare_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_spare(db, spare_id)


@router.get("/markets", response_model=list[MarketResponse])
def get_markets(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return list_markets(db, page, page_size)


@router.get("/markets/{market_id}", response_model=MarketResponse)
def get_market_by_id(
    market_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_market(db, market_id)


@router.get("/equipment", response_model=list[EquipmentResponse])
def get_equipment_list(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return list_equipment(db, page, page_size)


@router.get("/equipment/{equipment_id}", response_model=EquipmentResponse)
def get_equipment_by_id_route(
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_equipment_by_id(db, equipment_id)


@router.get("/labsdls", response_model=list[LabsdlResponse])
def get_labsdls(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
    page: int = 1,
    page_size: int = 50,
):
    return list_labsdls(db, page, page_size)


@router.get("/labsdls/{labsdl_id}", response_model=LabsdlResponse)
def get_labsdl_by_id(
    labsdl_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_labsdl(db, labsdl_id)
