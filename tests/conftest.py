from pathlib import Path
from tempfile import mkstemp
from typing import Generator, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.models.base import Base
from app.models.fsm_user import FSMUser
from app.models.master import Market, Equipment, Technician, Spare, Labsdl
from app.core.security import hash_password
from app.server import create_app


_fd, _db_path = mkstemp(suffix=".db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_db_path}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    Path(_db_path).unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def transaction() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(app: FastAPI) -> dict:
    db = TestingSessionLocal()
    user = FSMUser(
        email="test@example.com",
        user_name="Test User",
        passwd=hash_password("password123"),
        user_role="TECHNICIAN",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return {
        "user_id": user.user_id,
        "email": user.email,
        "user_name": user.user_name,
        "password": "password123",
    }


@pytest.fixture
def auth_headers(client: TestClient, test_user: dict) -> dict:
    response = client.post("/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_market(db_session: Session) -> Market:
    market = Market(market_name="Test Market", city="Test City", transport_cost=100)
    db_session.add(market)
    db_session.commit()
    db_session.refresh(market)
    return market


@pytest.fixture
def test_equipment(db_session: Session) -> Equipment:
    equipment = Equipment(equipment_name="Test Equipment")
    db_session.add(equipment)
    db_session.commit()
    db_session.refresh(equipment)
    return equipment


@pytest.fixture
def test_labsdl(db_session: Session) -> Labsdl:
    labsdl = Labsdl(labsdl_name="Normal", labsdl_description="", hourly_rate=50)
    db_session.add(labsdl)
    db_session.commit()
    db_session.refresh(labsdl)
    return labsdl


@pytest.fixture
def test_technician(db_session: Session, test_user: dict) -> Technician:
    technician = Technician(user_id=test_user["user_id"])
    db_session.add(technician)
    db_session.commit()
    db_session.refresh(technician)
    return technician


@pytest.fixture
def test_spare(db_session: Session) -> Spare:
    spare = Spare(spare_name="Test Spare", unit="pcs", price=10)
    db_session.add(spare)
    db_session.commit()
    db_session.refresh(spare)
    return spare
