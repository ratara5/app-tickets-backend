from datetime import datetime

from fastapi.testclient import TestClient

from app.models.master import Market, Equipment, Technician


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket for maintenance",
    "priority": "NORMAL",
    "status": "OPEN",
    "market_id": 1,
    "equipment_id": 1,
}


def _create_assigned_started_ticket(
    client: TestClient, auth_headers: dict
) -> int:
    resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    return ticket_id


def test_create_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ticket_id"] == ticket_id


def test_create_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.post(
        "/maintenances",
        json={
            "maintenance_id": "00000000-0000-0000-0000-000000000001",
            "ticket_id": 1,
            "maintenance_date": datetime.now().isoformat(),
        }
    )
    assert response.status_code == 401


def test_create_maintenance_invalid_data(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post("/maintenances", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_list_maintenances(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/maintenances", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_maintenances_unauthorized(
    client: TestClient
) -> None:
    response = client.get("/maintenances")
    assert response.status_code == 401


def test_get_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000002"
    create_resp = client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    mid = create_resp.json()["maintenance_id"]
    response = client.get(f"/maintenances/{mid}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["maintenance_id"] == mid


def test_get_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get(
        "/maintenances/00000000-0000-0000-0000-000000000099",
        headers=auth_headers
    )
    assert response.status_code == 404


def test_get_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.get("/maintenances/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 401


def test_update_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000001",
        data={"payload": '{"maintenance_description": "Updated"}'}
    )
    assert response.status_code == 401


def test_update_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000099",
        data={"payload": '{"maintenance_description": "Updated"}'},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_pause_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000003"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    response = client.patch(
        f"/maintenances/{maintenance_id}/pause",
        json={"pause_reason": "Test pause"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PAUSED"


def test_pause_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000001/pause",
        json={"pause_reason": "Test"}
    )
    assert response.status_code == 401


def test_pause_maintenance_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/maintenances/00000000-0000-0000-0000-000000000099/pause",
        json={"pause_reason": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_delete_maintenance_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    ticket_id = _create_assigned_started_ticket(client, auth_headers)
    maintenance_id = "00000000-0000-0000-0000-000000000004"
    client.post(
        "/maintenances",
        json={
            "maintenance_id": maintenance_id,
            "ticket_id": ticket_id,
            "maintenance_date": datetime.now().isoformat(),
        },
        headers=auth_headers
    )
    response = client.delete(
        f"/maintenances/{maintenance_id}",
        headers=auth_headers
    )
    assert response.status_code == 204


def test_delete_maintenance_unauthorized(
    client: TestClient
) -> None:
    response = client.delete(
        "/maintenances/00000000-0000-0000-0000-000000000001"
    )
    assert response.status_code == 401
