## Why

The backend currently lacks API endpoints for reading master and catalog data (Technicians, Spares, Markets, Equipment, Labsdl). Frontend and external integrations need read-only access to this reference data for selection dropdowns, validation, and display purposes. Without these endpoints, consumers must hardcode or duplicate this data.

## What Changes

- Add `GET /technicians` and `GET /technicians/{technician_id}` endpoints
- Add `GET /spares` and `GET /spares/{spare_id}` endpoints
- Add `GET /markets` and `GET /markets/{market_id}` endpoints
- Add `GET /equipments` and `GET /equipments/{equipment_id}` endpoints
- Add `GET /labsdls` and `GET /labsdls/{labsdl_id}` endpoints
- Create Pydantic schemas for request/response serialization for all five models
- Create repository layer (get_all, get_by_id) for all five models
- Create service layer with serialization for all five models
- Update `docs/api-spec.yml` with new endpoint definitions
- Update `README.md` with new route documentation
- Update Postman collection with new request examples

## Capabilities

### New Capabilities
- `master-data-api`: Read-only API endpoints for master and catalog tables (technicians, spares, markets, equipment, labsdls) with list and single-record retrieval

### Modified Capabilities
<!-- No existing specs are modified -->

## Impact

- **New files**: `app/schemas/master.py`, `app/repositories/master_repo.py`, `app/services/master_service.py`, `app/api/routes/master.py`
- **Modified files**: `app/api/routes/__init__.py`, `docs/api-spec.yml`, `README.md`, `app-tickets-backend.postman_collection.json`
- **No database changes** — models already exist in `master.py`
- **No dependency changes**
