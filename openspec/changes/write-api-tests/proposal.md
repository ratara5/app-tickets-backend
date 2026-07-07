## Why

Only 11 auth tests exist for 23 API endpoints. The backend has zero tests for tickets, maintenances, uploads, and worksheets, making it impossible to verify correctness during refactoring or feature additions. Comprehensive tests are needed to prevent regressions, document expected behavior, and enable safe iteration.

## What Changes

- Create factory_boy factories for all 16 SQLAlchemy models to simplify test data setup
- Add API integration tests for all 4 untested endpoint groups (tickets, maintenances, uploads, worksheets)
- Follow existing test patterns: pytest + httpx TestClient, SQLite test DB, autouse fixtures
- Each endpoint group gets its own test file covering: happy path, validation errors, auth errors, not-found, and business logic errors

## Capabilities

### New Capabilities

- `api-testing`: Automated API integration tests covering all endpoint groups (tickets, maintenances, uploads, worksheets), factory_boy factories for test data, and reusable test utilities

### Modified Capabilities

<!-- No existing capabilities to modify -->

## Impact

- `tests/` directory: 4 new test files (`test_tickets.py`, `test_maintenances.py`, `test_uploads.py`, `test_worksheets.py`)
- `tests/`: New `factories.py` with factory_boy factories for all models
- `tests/conftest.py`: Minor additions (new fixtures for tickets, maintenances, etc.)
- No impact on production code, routes, or database schema
