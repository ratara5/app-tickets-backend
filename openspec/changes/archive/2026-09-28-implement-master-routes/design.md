## Context

The `app/models/master.py` file defines five SQLAlchemy models — `Technician`, `Spare`, `Market`, `Equipment`, `Labsdl` — but none have API endpoints, schemas, services, or repositories. The existing CRUD pattern (tickets, maintenances) follows a consistent three-layer architecture: Route → Service → Repository, with JWT authentication on all endpoints.

## Goals / Non-Goals

**Goals:**
- Expose read-only GET endpoints (list + by-id) for all five master/catalog models
- Follow the existing three-layer architecture (route → service → repository) exactly
- Reuse existing patterns: JWT auth dependency, pagination, response serialization
- Update all documentation artifacts (api-spec, README, Postman)

**Non-Goals:**
- No CREATE, UPDATE, or DELETE endpoints — no mutation of master data via API
- No database migrations or model changes
- No new dependencies or infrastructure changes
- No generic/reusable CRUD base classes — each model gets explicit functions

## Decisions

1. **One file per layer, not per model** — A single `master.py` per layer (schemas, repositories, services, routes) groups all five models together. This avoids file sprawl while keeping each layer cohesive. Alternative considered: one file per model (e.g., `technician_repo.py`, `spare_repo.py`) — rejected because it would add 15+ files for near-identical logic.

2. **Explicit per-model functions, not a generic CRUD base** — Each model gets its own `get_all_{model}s()` and `get_{model}_by_id()` functions in the repository and service layers. Alternative considered: a generic `MasterRepository(BaseRepository[ModelT])` — rejected because it adds abstraction without benefit for only 2 operations × 5 models.

3. **Flat response schemas** — Each master/catalog table maps to one response schema exposing all columns directly (no nested joins). Alternative considered: include related data (e.g., technician's user name via `user_id` FK) — rejected for MVP; join complexity can be added later when a consumer needs it.

4. **Pagination on list endpoints** — `page` and `page_size` query params, defaulting to `page=1, page_size=50`, matching the ticket pattern. Alternative considered: no pagination — rejected because master tables could grow large (especially technicians and spares).

5. **JWT auth required** — All endpoints require a valid token via `get_current_user`. Alternative considered: public endpoints — rejected because master data (especially technician assignments) is internal.

6. **Single router file** — One `master.py` route file with a single `APIRouter(prefix="")` defining all 10 endpoints (5 × {list, by-id}). Alternative considered: separate routers per model — rejected; 10 endpoints in one file is manageable and keeps registration in `__init__.py` simple.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Technician model references `FSMUser` via `user_id` — flat response lacks user name | Add `technician_name` or similar field to response schema in a follow-up if frontend requests it |
| Spare `price` is `Decimal` — JSON serialization edge cases | FastAPI handles `Decimal` → `float` implicitly; tests should cover edge values |
| No filtering/search on list endpoints | Acceptable for MVP; can add query param filters later without breaking changes |
