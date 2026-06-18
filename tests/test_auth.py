from fastapi.testclient import TestClient
from app.core.security import hash_password, create_access_token


def test_register_success(client: TestClient) -> None:
    response = client.post("/auth/register", json={
        "email": "new@example.com",
        "password": "securepass",
        "user_name": "New User",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email(client: TestClient, test_user: dict) -> None:
    response = client.post("/auth/register", json={
        "email": test_user["email"],
        "password": "anotherpass",
        "user_name": "Another User",
    })
    assert response.status_code == 409


def test_register_missing_fields(client: TestClient) -> None:
    response = client.post("/auth/register", json={
        "email": "no@name.com",
    })
    assert response.status_code == 422


def test_login_success(client: TestClient, test_user: dict) -> None:
    response = client.post("/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client: TestClient) -> None:
    response = client.post("/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "wrong",
    })
    assert response.status_code == 401


def test_logout_success(client: TestClient, auth_headers: dict) -> None:
    response = client.post("/auth/logout", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Logged out successfully"


def test_logout_invalid_token(client: TestClient) -> None:
    response = client.post("/auth/logout", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_get_me_authenticated(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "email" in data
    assert "user_name" in data
    assert "user_role" in data


def test_get_me_unauthenticated(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_update_me_authenticated(client: TestClient, auth_headers: dict) -> None:
    response = client.put("/auth/me", json={
        "user_name": "Updated Name",
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["user_name"] == "Updated Name"


def test_update_me_unauthenticated(client: TestClient) -> None:
    response = client.put("/auth/me", json={"user_name": "Hacker"})
    assert response.status_code == 401


def test_blacklisted_token_rejected(client: TestClient, test_user: dict) -> None:
    login_resp = client.post("/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"],
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/auth/logout", headers=headers)

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
