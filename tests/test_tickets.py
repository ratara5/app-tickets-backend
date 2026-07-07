from datetime import datetime

from fastapi.testclient import TestClient

from app.models.master import Market, Equipment, Technician


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket description",
    "priority": "NORMAL",
    "status": "OPEN",
    "market_id": 1,
    "equipment_id": 1,
}


def test_create_ticket_success(
    client: TestClient, auth_headers: dict, test_market: Market, test_equipment: Equipment
) -> None:
    response = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["ticket_description"] == "Test ticket description"


def test_create_ticket_unauthorized(client: TestClient) -> None:
    response = client.post("/tickets", json=TICKET_PAYLOAD)
    assert response.status_code == 401


def test_create_ticket_invalid_data(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post("/tickets", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_list_tickets(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/tickets", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_tickets_unauthorized(client: TestClient) -> None:
    response = client.get("/tickets")
    assert response.status_code == 401


def test_get_ticket_success(
    client: TestClient, auth_headers: dict, test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.get(f"/tickets/{ticket_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["ticket_id"] == ticket_id


def test_get_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/tickets/99999", headers=auth_headers)
    assert response.status_code == 404


def test_get_ticket_unauthorized(client: TestClient) -> None:
    response = client.get("/tickets/1")
    assert response.status_code == 401


def test_assign_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.patch(
        f"/tickets/{ticket_id}/assign",
        json={"technician_id": test_technician.technician_id},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ASSIGNED"


def test_assign_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.patch("/tickets/1/assign", json={})
    assert response.status_code == 401


def test_assign_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/tickets/99999/assign",
        json={},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_assign_ticket_invalid_state(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    response = client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    assert response.status_code in (400, 422)


def test_start_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    response = client.patch(
        f"/tickets/{ticket_id}/start",
        headers=auth_headers
    )
    assert response.status_code == 200


def test_start_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.patch("/tickets/1/start")
    assert response.status_code == 401


def test_start_ticket_invalid_state(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.patch(
        f"/tickets/{ticket_id}/start",
        headers=auth_headers
    )
    assert response.status_code in (400, 422)


def test_cancel_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.patch(
        f"/tickets/{ticket_id}/cancel",
        json={"cancellation_reason": "Test cancellation"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"


def test_cancel_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/tickets/1/cancel",
        json={"cancellation_reason": "Test"}
    )
    assert response.status_code == 401


def test_cancel_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.patch(
        "/tickets/99999/cancel",
        json={"cancellation_reason": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 404


def test_add_wkd_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment,
    test_technician: Technician
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    client.patch(
        f"/tickets/{ticket_id}/assign",
        json={},
        headers=auth_headers
    )
    client.patch(
        f"/tickets/{ticket_id}/start",
        headers=auth_headers
    )
    response = client.patch(
        f"/tickets/{ticket_id}/addwkd",
        json={
            "operation_percentage": 50,
            "market_temperature": 25,
            "operation_damage": False,
            "completed": False,
            "observations_wkd": "Test observations",
        },
        headers=auth_headers
    )
    assert response.status_code == 200


def test_add_wkd_unauthorized(
    client: TestClient
) -> None:
    response = client.patch(
        "/tickets/1/addwkd",
        json={
            "operation_percentage": 50,
            "market_temperature": 25,
            "operation_damage": False,
            "completed": False,
            "observations_wkd": "Test",
        }
    )
    assert response.status_code == 401


def test_delete_ticket_success(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment
) -> None:
    create_resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_resp.json()["ticket_id"]
    response = client.delete(f"/tickets/{ticket_id}", headers=auth_headers)
    assert response.status_code == 204


def test_delete_ticket_unauthorized(
    client: TestClient
) -> None:
    response = client.delete("/tickets/1")
    assert response.status_code == 401


def test_delete_ticket_not_found(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.delete("/tickets/99999", headers=auth_headers)
    assert response.status_code == 404
