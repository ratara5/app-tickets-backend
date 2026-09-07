# Tasks: Add 'SIGNED' Ticket Status after 'CLOSED'

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create feature branch `feature/add-signed-ticket-status` from main
- [x] 0.2 Verify branch creation and current branch status (`git branch --show-current`)

## 1. Backend: Add SIGNED Status to State Machine (TDD)

- [x] 1.1 Write failing tests for `TicketStatus` enum exposing `signed = "SIGNED"` right after `closed` (update `tests/test_tickets.py`)
- [x] 1.2 Write failing tests for `VALID_TRANSITIONS`: `CLOSED → SIGNED` allowed, no outgoing transitions from `SIGNED`, and non-`CLOSED` states cannot become `SIGNED`
- [x] 1.3 Implement `signed = "SIGNED"` in `TicketStatus` (`app/schemas/ticket.py`)
- [x] 1.4 Update `VALID_TRANSITIONS` in `app/services/ticket_service.py`: `TicketStatus.closed: [TicketStatus.signed]`, `TicketStatus.signed: []`
- [x] 1.5 Run the new state-machine tests and confirm they pass

## 2. Backend: Sign Action (TDD)

- [x] 2.1 Write failing tests for `POST /maintenances/{maintenance_id}/sign` covering spec scenarios: happy path (`CLOSED` + generated worksheet PDF → `SIGNED`), 422 when ticket not `CLOSED`, 409 when worksheet PDF missing, idempotent 200 when already `SIGNED`, 403 ownership violation, 404 missing maintenance
- [x] 2.2 Implement `sign_maintenance` service in `app/services/maintenance_service.py` (resolve maintenance → ticket, guard CLOSED, require worksheet `closed`/`pdf_path`, apply `SIGNED` transition, idempotent for already `SIGNED`, reuse `assert_ownership`)
- [x] 2.3 Register the route `POST /maintenances/{maintenance_id}/sign` in `app/api/routes/maintenances.py`
- [x] 2.4 Run the sign-endpoint tests and confirm they pass

## 3. Backend: Expose ticket_status on Maintenance Items (TDD)

- [x] 3.1 Write failing tests asserting `ticket_status` appears in maintenance list and single-item responses and reflects `SIGNED` after signing
- [x] 3.2 Implement `ticket_status` in `_serialize_maintenance_item` (`app/services/maintenance_service.py`) from `maintenance.ticket.status`
- [x] 3.3 Add `ticket_status` to `MaintenanceItemResponse` (`app/schemas/maintenance.py`)
- [x] 3.4 Run the serialization tests and confirm they pass

## 4. Backend: Review and Update Existing Unit Tests (MANDATORY)

- [x] 4.1 Review `tests/test_tickets.py`, `tests/test_maintenances.py`, and `tests/test_worksheets.py` for assertions that enumerate statuses or assume `CLOSED` is terminal; update them to reflect `SIGNED`
- [x] 4.2 Confirm factories/seed data in `tests/factories.py` do not need new status values; update if needed
- [x] 4.3 Run the targeted test files and confirm no regressions

## 5. Backend: Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 5.1 Prepare test environment (Docker PostgreSQL up, dependencies installed) and capture pre-test database baseline (counts of `tickets`/`maintenances`/`worksheets`)
- [ ] 5.2 Run targeted unit tests: `pytest tests/test_tickets.py tests/test_maintenances.py tests/test_worksheets.py -v`
- [ ] 5.3 Run broader suite with coverage: `pytest --cov=app --cov-report=term-missing` (minimum 80%)
- [ ] 5.4 Verify post-test database state matches the baseline; restore if needed
- [ ] 5.5 Create report `openspec/changes/add-signed-ticket-status/specs/ticket-signed-status/reports/YYYY-MM-DD-step-5-unit-test-and-db-verification.md` (AGENT MUST EXECUTE)

## 6. Backend: Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 6.1 Start the backend server (`uvicorn app.main:app --reload`) and confirm DB connectivity
- [ ] 6.2 Authenticate and obtain a JWT token; create (or reuse) a `CLOSED` ticket with expected worksheet PDF in place
- [ ] 6.3 `POST /maintenances/{maintenance_id}/sign` happy path: assert 200 and `ticket_status: "SIGNED"`, then restore DB state
- [ ] 6.4 Error cases with curl: ticket not `CLOSED` (422), worksheet PDF missing (409), already `SIGNED` idempotent (200), missing maintenance (404), unauthorized/forbidden (401/403)
- [ ] 6.5 Verify database state matches pre-test state after all curl testing

## 7. E2E Testing (MANDATORY if applicable - AGENT MUST EXECUTE)

- [ ] 7.1 Confirm API contract exposes the `sign` endpoint and `ticket_status` field by checking the regenerated `docs/api-spec.json`
- [ ] 7.2 Mark N/A for mobile E2E in this repo: frontend is a separate React Native project (Detox/Maestro handled there)

## 8. Update API Contract and Technical Documentation (MANDATORY)

- [ ] 8.1 Update `docs/api-spec.yml` with the `POST /maintenances/{maintenance_id}/sign` operation and `ticket_status` field on maintenance schemas
- [ ] 8.2 Regenerate `docs/api-spec.json` from the running server (`curl http://localhost:8000/openapi.json -o docs/api-spec.json` or `scripts/export_openapi.py`)
- [ ] 8.3 Update `docs/data-model.md` only if it enumerates ticket status values
- [ ] 8.4 Update `docs/backend-standards.md` or `docs/development_guide.md` if patterns or setup steps changed (otherwise mark N/A)