from fastapi.testclient import TestClient
from tests.conftest import engine, TestingSessionLocal, override_get_db
from app.models.base import Base
from app.core.database import get_db
from app.server import create_app
from app.core.security import hash_password
from app.models.fsm_user import FSMUser
import tests.test_worksheets as tw

Base.metadata.create_all(bind=engine)
db = TestingSessionLocal()
u = FSMUser(email="test@example.com", user_name="Test User", passwd=hash_password("password123"), user_role="TECHNICIAN")
db.add(u); db.commit(); db.close()

application = create_app()
application.dependency_overrides[get_db] = override_get_db
c = TestClient(application)
r = c.post("/auth/login", json={"email": "test@example.com", "password": "password123"})
print("LOGIN", r.status_code)
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
r2 = c.post("/tickets", json=tw.TICKET_PAYLOAD, headers=h)
print("POST /tickets", r2.status_code)
print(r2.text[:600])
