from datetime import datetime

from fastapi.testclient import TestClient

from app.models.master import Market, Equipment, Technician


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket for worksheet",
    "priority": "NORMAL",
    "status": "OPEN",
}


def _create_maintenance(
    client: TestClient, auth_headers: dict
) -> str:
    resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000010"
    resp = client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    return resp.json()["maintenance_id"]


def test_get_worksheet_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    mid = _create_maintenance(client, auth_headers)
    response = client.get(
        f"/maintenances/{mid}/worksheet",
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "worksheet_id" in data
    assert data["maintenance_id"] == mid


def test_get_worksheet_unauthorized(
    client: TestClient
) -> None:
    response = client.get(
        "/maintenances/00000000-0000-0000-0000-000000000001/worksheet"
    )
    assert response.status_code == 401


def test_get_worksheet_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get(
        "/maintenances/00000000-0000-0000-0000-000000000099/worksheet",
        headers=auth_headers
    )
    assert response.status_code == 404


def test_update_worksheet_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    mid = _create_maintenance(client, auth_headers)
    response = client.patch(
        f"/maintenances/{mid}/worksheet",
        json={
            "receiver_name": "John Doe",
            "receiver_doc_id": "1234567890",
        },
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["receiver_name"] == "John Doe"


def test_update_worksheet_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000001/worksheet",
        json={"receiver_name": "Hacker"}
    )
    assert response.status_code == 401


def test_update_worksheet_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000099/worksheet",
        json={"receiver_name": "John Doe"},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_generate_pdf_unauthorized(
    client: TestClient
) -> None:
    response = client.post(
        "/maintenances/00000000-0000-0000-0000-000000000001/worksheet/generate-pdf"
    )
    assert response.status_code == 401


def test_generate_pdf_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/maintenances/00000000-0000-0000-0000-000000000099/worksheet/generate-pdf",
        headers=auth_headers
    )
    assert response.status_code == 404
