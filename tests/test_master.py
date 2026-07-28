from fastapi.testclient import TestClient

from app.models.master import Market, Equipment, Technician, Spare, Labsdl


class TestTechnicians:
    def test_list_technicians(self, client: TestClient, auth_headers: dict, test_technician: Technician) -> None:
        response = client.get("/technicians", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(t["technician_id"] == test_technician.technician_id for t in data)

    def test_get_technician_by_id(self, client: TestClient, auth_headers: dict, test_technician: Technician) -> None:
        response = client.get(f"/technicians/{test_technician.technician_id}", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["technician_id"] == test_technician.technician_id
        assert body["user_name"] == "Test User"

    def test_get_technician_not_found(self, client: TestClient, auth_headers: dict) -> None:
        response = client.get("/technicians/9999", headers=auth_headers)
        assert response.status_code == 404

    def test_technicians_unauthorized(self, client: TestClient) -> None:
        response = client.get("/technicians")
        assert response.status_code == 401
        response = client.get("/technicians/1")
        assert response.status_code == 401


class TestSpares:
    def test_list_spares(self, client: TestClient, auth_headers: dict, test_spare: Spare) -> None:
        response = client.get("/spares", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(s["spare_id"] == test_spare.spare_id for s in data)

    def test_get_spare_by_id(self, client: TestClient, auth_headers: dict, test_spare: Spare) -> None:
        response = client.get(f"/spares/{test_spare.spare_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["spare_id"] == test_spare.spare_id

    def test_get_spare_not_found(self, client: TestClient, auth_headers: dict) -> None:
        response = client.get("/spares/9999", headers=auth_headers)
        assert response.status_code == 404

    def test_spares_unauthorized(self, client: TestClient) -> None:
        response = client.get("/spares")
        assert response.status_code == 401


class TestMarkets:
    def test_list_markets(self, client: TestClient, auth_headers: dict, test_market: Market) -> None:
        response = client.get("/markets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(m["market_id"] == test_market.market_id for m in data)

    def test_get_market_by_id(self, client: TestClient, auth_headers: dict, test_market: Market) -> None:
        response = client.get(f"/markets/{test_market.market_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["market_id"] == test_market.market_id

    def test_get_market_not_found(self, client: TestClient, auth_headers: dict) -> None:
        response = client.get("/markets/9999", headers=auth_headers)
        assert response.status_code == 404

    def test_markets_unauthorized(self, client: TestClient) -> None:
        response = client.get("/markets")
        assert response.status_code == 401


class TestEquipment:
    def test_list_equipment(self, client: TestClient, auth_headers: dict, test_equipment: Equipment) -> None:
        response = client.get("/equipments", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(e["equipment_id"] == test_equipment.equipment_id for e in data)

    def test_get_equipment_by_id(self, client: TestClient, auth_headers: dict, test_equipment: Equipment) -> None:
        response = client.get(f"/equipments/{test_equipment.equipment_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["equipment_id"] == test_equipment.equipment_id

    def test_get_equipment_not_found(self, client: TestClient, auth_headers: dict) -> None:
        response = client.get("/equipments/9999", headers=auth_headers)
        assert response.status_code == 404

    def test_equipment_unauthorized(self, client: TestClient) -> None:
        response = client.get("/equipments")
        assert response.status_code == 401


class TestLabsdls:
    def test_list_labsdls(self, client: TestClient, auth_headers: dict, test_labsdl: Labsdl) -> None:
        response = client.get("/labsdls", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(l["labsdl_id"] == test_labsdl.labsdl_id for l in data)

    def test_get_labsdl_by_id(self, client: TestClient, auth_headers: dict, test_labsdl: Labsdl) -> None:
        response = client.get(f"/labsdls/{test_labsdl.labsdl_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["labsdl_id"] == test_labsdl.labsdl_id

    def test_get_labsdl_not_found(self, client: TestClient, auth_headers: dict) -> None:
        response = client.get("/labsdls/9999", headers=auth_headers)
        assert response.status_code == 404

    def test_labsdls_unauthorized(self, client: TestClient) -> None:
        response = client.get("/labsdls")
        assert response.status_code == 401
