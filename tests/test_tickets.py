from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.models.master import Market, Equipment, Technician
from app.schemas.ticket import TicketStatus
from app.services.ticket_service import VALID_TRANSITIONS, validate_transition


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
    # Idempotent start contract: fresh creation returns 201 with the
    # enriched MaintenanceItemResponse shape.
    assert response.status_code == 201
    data = response.json()
    assert data["maintenance_id"]
    assert data["ticket_id"] == ticket_id
    assert "maintenance_date" in data
    assert "maintenance_description" in data


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


# ── SIGNED ticket status (change: add-signed-ticket-status) ────────────────────


def test_ticket_status_exposes_signed_after_closed() -> None:
    statuses = list(TicketStatus)
    assert TicketStatus.signed == "SIGNED"
    assert statuses.index(TicketStatus.signed) == statuses.index(TicketStatus.closed) + 1


def test_valid_transitions_allow_closed_to_signed() -> None:
    assert VALID_TRANSITIONS[TicketStatus.closed] == [TicketStatus.signed]


def test_valid_transitions_signed_has_no_outgoing() -> None:
    assert VALID_TRANSITIONS[TicketStatus.signed] == []


def test_validate_transition_accepts_closed_to_signed() -> None:
    validate_transition(TicketStatus.closed, TicketStatus.signed)


def test_validate_transition_rejects_signed_as_source() -> None:
    for target in TicketStatus:
        with pytest.raises(HTTPException):
            validate_transition(TicketStatus.signed, target)


def test_validate_transition_rejects_non_closed_sources_to_signed() -> None:
    for source in TicketStatus:
        if source == TicketStatus.closed:
            continue
        with pytest.raises(HTTPException):
            validate_transition(source, TicketStatus.signed)
