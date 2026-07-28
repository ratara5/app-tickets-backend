## 1. Schemas

- [x] 1.1 Create `app/schemas/master.py` with Pydantic response schemas: `TechnicianResponse`, `SpareResponse`, `MarketResponse`, `EquipmentResponse`, `LabsdlResponse`, each with `ConfigDict(from_attributes=True)`

## 2. Repositories

- [x] 2.1 Create `app/repositories/master_repo.py` with `get_all_technicians()`, `get_technician_by_id()`, `get_all_spares()`, `get_spare_by_id()`, `get_all_markets()`, `get_market_by_id()`, `get_all_equipment()`, `get_equipment_by_id()`, `get_all_labsdls()`, `get_labsdl_by_id()` following logic in repositories/ticket_repo.py (`_get_query()` called for get one and called for get all, obviously without date filter)

## 3. Services

- [x] 3.1 Create `app/services/master_service.py` with `list_technicians()`, `get_technician()`, `list_spares()`, `get_spare()`, `list_markets()`, `get_market()`, `list_equipment()`, `get_equipment()`, `list_labsdls()`, `get_labsdl()` — each calling the corresponding repo function with pagination support for list variants

## 4. Routes

- [x] 4.1 Create `app/api/routes/master.py` with `APIRouter` and 10 endpoints: `GET /technicians`, `GET /technicians/{technician_id}`, `GET /spares`, `GET /spares/{spare_id}`, `GET /markets`, `GET /markets/{market_id}`, `GET /equipment`, `GET /equipment/{equipment_id}`, `GET /labsdls`, `GET /labsdls/{labsdl_id}`
- [x] 4.2 Register `master_router` in `app/api/routes/__init__.py`

## 5. Tests

- [x] 5.1 Create tests for master repositories (covered by integration tests)
- [x] 5.2 Create tests for master services (covered by integration tests)
- [x] 5.3 Create tests for master API routes (list + by-id per model, 404 cases, auth)

## 6. Documentation

- [x] 6.1 Add new endpoint definitions to `docs/api-spec.yml`
- [x] 6.2 Add new route section to `README.md`
- [x] 6.3 Add "Master Data" folder with all endpoints to `app-tickets-backend.postman_collection.json`
