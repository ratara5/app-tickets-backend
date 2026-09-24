from datetime import datetime
import base64
import json
import os
import struct
import uuid
import zlib

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from weasyprint import HTML as WeasyHTML

from app.models.master import Market, Equipment, Technician
from app.models.worksheet import Worksheet


def _uuid7_str() -> str:
    """Build a v7 UUID string (workaround: uuid.uuid7 needs Python >= 3.14)."""
    b = bytearray(os.urandom(16))
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


TICKET_PAYLOAD = {
    "ticket_id": "1",
    "ticket_date": datetime.now().isoformat(),
    "ticket_description": "Test ticket for worksheet",
    "priority": "NORMAL",
    "status": "OPEN",
    "market_id": 1,
    "equipment_id": 1,
}


def _create_maintenance(
    client: TestClient, auth_headers: dict
) -> str:
    resp = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = resp.json()["ticket_id"]
    client.patch(f"/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    start_resp = client.patch(f"/tickets/{ticket_id}/start", headers=auth_headers)
    assert start_resp.status_code == 201, start_resp.text
    return start_resp.json()["maintenance_id"]


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
        f"/maintenances/{_uuid7_str()}/worksheet",
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
        f"/maintenances/{_uuid7_str()}/worksheet",
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
        f"/maintenances/{_uuid7_str()}/worksheet/generate-pdf",
        headers=auth_headers
    )
    assert response.status_code == 404


def _close_ticket(client: TestClient, auth_headers: dict, mid: str) -> None:
    """PATCH the maintenance, which moves the owner ticket to CLOSED (weekday)."""
    resp = client.patch(
        f"/maintenances/{mid}",
        data={"payload": json.dumps({"maintenance_description": "Closed maintenance"})},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


def test_generate_pdf_success(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
    monkeypatch,
) -> None:
    """generate-pdf renders the template, closes the sheet and returns a URL."""
    mid = _create_maintenance(client, auth_headers)
    _close_ticket(client, auth_headers, mid)

    resp = client.get(f"/maintenances/{mid}/worksheet", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    # Fake the external renderer + MinIO so the test needs no weasyprint/storage.
    class _FakeHtml:
        def write_pdf(self) -> bytes:
            return b"%PDF-1.4 mock worksheet pdf"

    monkeypatch.setattr(
        "app.services.worksheet_service.HTML", lambda *args, **kwargs: _FakeHtml()
    )

    uploaded: dict = {}

    def fake_upload_file(file_stream, original_filename, content_type, full_object_path, job_id=""):
        uploaded["path"] = full_object_path
        return {}

    monkeypatch.setattr("app.services.worksheet_service.upload_file", fake_upload_file)
    monkeypatch.setattr(
        "app.services.worksheet_service.get_presigned_url",
        lambda object_name, expires_hours=1: f"https://minio.local/{object_name}",
    )

    response = client.post(
        f"/maintenances/{mid}/worksheet/generate-pdf", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sheet_number"]
    assert data["url"].startswith("https://minio.local/")
    assert data["generated_at"]

    db_session.expire_all()
    ws = db_session.query(Worksheet).filter(
        Worksheet.maintenance_id == uuid.UUID(mid)
    ).first()
    assert ws is not None
    assert ws.closed is True
    assert ws.pdf_path == uploaded["path"]
    assert ws.sheet_number == data["sheet_number"]


def test_generate_pdf_renders_technician_rows(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
    monkeypatch,
) -> None:
    """The generated PDF HTML includes every maintenance technician row with
    HH:MM start/end hours (the template must iterate `technicians`, not the
    undefined `tecnicos`/bare `start_hour`/`end_hour`)."""
    mid = _create_maintenance(client, auth_headers)

    # Close the ticket AND attach a technician with hours in one save (JSON
    # payload, matching how the mobile app submits the maintenance form).
    resp = client.patch(
        f"/maintenances/{mid}",
        data={
            "payload": json.dumps({
                "maintenance_description": "Closed maintenance",
                "technicians": [{
                    "technician_id": test_technician.technician_id,
                    "start_hour": "08:00",
                    "end_hour": "17:00",
                }],
            })
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    captured: dict = {}

    class _FakeHtml:
        def __init__(self, *args, **kwargs) -> None:
            captured["html"] = kwargs.get("string", "")

        def write_pdf(self) -> bytes:
            return b"%PDF-1.4 mock worksheet pdf"

    monkeypatch.setattr("app.services.worksheet_service.HTML", _FakeHtml)
    monkeypatch.setattr(
        "app.services.worksheet_service.upload_file", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        "app.services.worksheet_service.get_presigned_url",
        lambda object_name, expires_hours=1: f"https://minio.local/{object_name}",
    )

    response = client.post(
        f"/maintenances/{mid}/worksheet/generate-pdf", headers=auth_headers
    )
    assert response.status_code == 200, response.text

    html = captured["html"]
    assert "CONSTANCIA REALIZACIÓN ASISTENCIA" in html
    # technician name resolves through fsm_user.user_name ("Test User")
    assert "Test User" in html
    assert "08:00" in html
    assert "17:00" in html
    # the buggy template never reaches the undefined `tecnicos` variable
    assert "tecnicos" not in html


def test_generate_pdf_ticket_not_closed(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
) -> None:
    mid = _create_maintenance(client, auth_headers)

    response = client.post(
        f"/maintenances/{mid}/worksheet/generate-pdf", headers=auth_headers
    )
    assert response.status_code == 409, response.text


def test_generate_pdf_closed_sheet_returns_fresh_url(
    client: TestClient, auth_headers: dict, db_session: Session,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
    monkeypatch,
) -> None:
    """Calling generate-pdf again on a closed sheet reuses the stored PDF."""
    mid = _create_maintenance(client, auth_headers)
    _close_ticket(client, auth_headers, mid)

    resp = client.get(f"/maintenances/{mid}/worksheet", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ws = db_session.query(Worksheet).filter(
        Worksheet.maintenance_id == uuid.UUID(mid)
    ).first()
    assert ws is not None
    ws.closed = True
    ws.pdf_path = "Maintenances/already-signed.pdf"
    ws.sheet_number = "WS-2026-000042"
    db_session.commit()

    monkeypatch.setattr(
        "app.services.worksheet_service.get_presigned_url",
        lambda object_name, expires_hours=1: f"https://minio.local/{object_name}",
    )
    monkeypatch.setattr("app.services.worksheet_service.upload_file", lambda *a, **k: {})

    response = client.post(
        f"/maintenances/{mid}/worksheet/generate-pdf", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["url"] == "https://minio.local/Maintenances/already-signed.pdf"
    assert response.json()["sheet_number"] == "WS-2026-000042"


def _mini_png_base64() -> str:
    """Build a tiny valid RGBA PNG (2x2) as a stand-in drawn signature."""
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"\x00\x00\x00\x00\xff\x00\x00\x00\xff" + b"\x00\x00\x00\x00\xff\x00\x00\x00\xff"
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")


def test_generate_pdf_is_one_page_with_visible_signature(
    client: TestClient, auth_headers: dict,
    test_market: Market, test_equipment: Equipment, test_technician: Technician,
    monkeypatch,
) -> None:
    """A signed worksheet PDF renders as a single Letter page and keeps the
    "CONSTANCIA … / DATOS DE QUIEN RECIBE" block — receiver data, technician rows
    and the Firma box with the signature image — intact on that page (it must not
    be pushed to a fragmentary second page, which made the signature invisible)."""
    mid = _create_maintenance(client, auth_headers)

    resp = client.patch(
        f"/maintenances/{mid}",
        data={
            "payload": json.dumps({
                "maintenance_description": "Closed maintenance",
                "technicians": [{
                    "technician_id": test_technician.technician_id,
                    "start_hour": "08:00",
                    "end_hour": "17:00",
                }],
            })
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    signature = _mini_png_base64()
    resp = client.patch(
        f"/maintenances/{mid}/worksheet",
        json={
            "receiver_name": "Receiver Name",
            "receiver_doc_id": "123456",
            "receiver_position": "Store Manager",
            "receiver_sap": "SAP-01",
            "receiver_signature": signature,
            "receiver_signature_timestamp": datetime.now().isoformat(),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    rendered: dict = {}

    class _RecordingHtml:
        """Wrap the real WeasyPrint HTML so rendering still runs for real while
        capturing the html string and the resulting document (for page count)."""

        def __init__(self, *args, **kwargs) -> None:
            rendered["html"] = kwargs.get("string", "")
            self._inner = WeasyHTML(*args, **kwargs)

        def write_pdf(self) -> bytes:
            rendered["document"] = self._inner.render()
            return self._inner.write_pdf()

    monkeypatch.setattr("app.services.worksheet_service.HTML", _RecordingHtml)
    monkeypatch.setattr("app.services.worksheet_service.upload_file", lambda *a, **k: {})
    monkeypatch.setattr(
        "app.services.worksheet_service.get_presigned_url",
        lambda object_name, expires_hours=1: f"https://minio.local/{object_name}",
    )

    response = client.post(
        f"/maintenances/{mid}/worksheet/generate-pdf", headers=auth_headers
    )
    assert response.status_code == 200, response.text

    html = rendered.get("html", "")
    document = rendered.get("document")
    assert "CONSTANCIA REALIZACIÓN ASISTENCIA" in html
    assert f"data:image/png;base64,{signature}" in html
    assert "Firma" in html
    assert document is not None
    assert len(document.pages) == 1, "Signed worksheet must fit a single page"
    assert signature in html
