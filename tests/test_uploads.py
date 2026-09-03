from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.models.master import Market, Equipment, Technician


PARENT_ID = str(uuid7())
BOGUS_UUID = str(uuid7())

UPLOAD_INIT_PAYLOAD = {
    "parent_tab": "maintenances",
    "parent_id": PARENT_ID,
    "tab_name": "photos",
    "col_name": "photo_file",
    "content_type": "image/jpeg",
    "total_size": 1024,
    "total_chunks": 1,
}


def test_init_upload_success(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/uploads/init",
        json=UPLOAD_INIT_PAYLOAD,
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "upload_id" in data
    assert "chunk_size" in data
    assert data["next_chunk"] == 0


def test_init_upload_unauthorized(
    client: TestClient
) -> None:
    response = client.post("/uploads/init", json=UPLOAD_INIT_PAYLOAD)
    assert response.status_code == 401


def test_init_upload_invalid_content_type(
    client: TestClient, auth_headers: dict
) -> None:
    payload = {**UPLOAD_INIT_PAYLOAD, "content_type": "application/x-unknown"}
    response = client.post("/uploads/init", json=payload, headers=auth_headers)
    assert response.status_code == 422


def test_init_upload_invalid_data(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post("/uploads/init", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_upload_chunk_success(
    client: TestClient, auth_headers: dict
) -> None:
    init_resp = client.post(
        "/uploads/init",
        json=UPLOAD_INIT_PAYLOAD,
        headers=auth_headers
    )
    upload_id = init_resp.json()["upload_id"]
    response = client.post(
        f"/uploads/chunk?upload_id={upload_id}&chunk_index=0",
        files={"chunk": ("test.jpg", b"test image data", "image/jpeg")},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["upload_id"] == upload_id


def test_upload_chunk_unauthorized(
    client: TestClient
) -> None:
    response = client.post(
        "/uploads/chunk?upload_id=test&chunk_index=0",
        files={"chunk": ("test.jpg", b"data", "image/jpeg")}
    )
    assert response.status_code == 401


def test_upload_chunk_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        f"/uploads/chunk?upload_id={BOGUS_UUID}&chunk_index=0",
        files={"chunk": ("test.jpg", b"data", "image/jpeg")},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_upload_chunk_invalid_index(
    client: TestClient, auth_headers: dict
) -> None:
    init_resp = client.post(
        "/uploads/init",
        json=UPLOAD_INIT_PAYLOAD,
        headers=auth_headers
    )
    upload_id = init_resp.json()["upload_id"]
    response = client.post(
        f"/uploads/chunk?upload_id={upload_id}&chunk_index=99",
        files={"chunk": ("test.jpg", b"data", "image/jpeg")},
        headers=auth_headers
    )
    assert response.status_code == 422


def test_upload_status_success(
    client: TestClient, auth_headers: dict
) -> None:
    init_resp = client.post(
        "/uploads/init",
        json=UPLOAD_INIT_PAYLOAD,
        headers=auth_headers
    )
    upload_id = init_resp.json()["upload_id"]
    response = client.get(
        f"/uploads/status/{upload_id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["upload_id"] == upload_id


def test_upload_status_unauthorized(
    client: TestClient
) -> None:
    response = client.get("/uploads/status/test-upload-id")
    assert response.status_code == 401


def test_upload_status_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get(
        f"/uploads/status/{BOGUS_UUID}",
        headers=auth_headers
    )
    assert response.status_code == 404


def test_complete_upload_unauthorized(
    client: TestClient
) -> None:
    response = client.post("/uploads/complete?upload_id=test")
    assert response.status_code == 401


def test_complete_upload_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        f"/uploads/complete?upload_id={BOGUS_UUID}",
        headers=auth_headers
    )
    assert response.status_code == 404


def test_complete_upload_success(
    client: TestClient, auth_headers: dict
) -> None:
    init_resp = client.post(
        "/uploads/init",
        json=UPLOAD_INIT_PAYLOAD,
        headers=auth_headers
    )
    upload_id = init_resp.json()["upload_id"]
    client.post(
        f"/uploads/chunk?upload_id={upload_id}&chunk_index=0",
        files={"chunk": ("test.jpg", b"test image data", "image/jpeg")},
        headers=auth_headers
    )
    response = client.post(
        f"/uploads/complete?upload_id={upload_id}",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completed"] is True


def test_init_upload_with_replaces_photo_id(
    client: TestClient, auth_headers: dict
) -> None:
    """POST /uploads/init accepts optional replaces_photo_id."""
    payload = {**UPLOAD_INIT_PAYLOAD, "replaces_photo_id": 42}
    response = client.post(
        "/uploads/init",
        json=payload,
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "upload_id" in data


def test_init_upload_replaces_photo_id_none(
    client: TestClient, auth_headers: dict
) -> None:
    """POST /uploads/init works without replaces_photo_id (default None)."""
    response = client.post(
        "/uploads/init",
        json=UPLOAD_INIT_PAYLOAD,
        headers=auth_headers
    )
    assert response.status_code == 201
