## Context

The backend has 23 API endpoints across 5 route groups (auth, tickets, maintenances, uploads, worksheets). Only auth has tests (11 tests in `tests/test_auth.py`). Tests use pytest with httpx TestClient against a FastAPI app backed by SQLite. A `tests/conftest.py` provides fixtures for app, client, test user, auth headers, and database transaction isolation.

The remaining 4 route groups have no tests. The test suite needs factories, endpoint tests, and possibly new fixtures to support them.

## Goals / Non-Goals

**Goals:**
- Create factory_boy factories for all 16 SQLAlchemy models for reusable test data
- Add API integration tests for all tickets, maintenance, upload, and worksheet endpoints
- Cover happy paths, validation errors, auth errors, not-found, and business logic errors per endpoint
- Maintain existing test patterns (httpx TestClient, SQLite, autouse transaction isolation)
- Achieve minimum 80% code coverage on routes layer

**Non-Goals:**
- Unit tests for services or repositories in isolation (covered by API integration tests)
- End-to-end tests against real PostgreSQL or MinIO (stays with SQLite in-memory)
- CI/CD pipeline configuration
- Performance or load tests

## Decisions

1. **factory_boy over plain fixtures**: The existing pattern creates test users inline. Factory Boy provides reusable, composable factories with sensible defaults, reducing boilerplate when creating related models (e.g., Ticket with nested Maintenance).

2. **One test file per route group**: Follow the existing `test_auth.py` pattern. Each file tests one router module, making it easy to find tests by domain.

3. **No async tests**: The existing tests are synchronous using httpx TestClient. The route handlers use `async def`, but TestClient handles the async loop internally. We stay synchronous to match existing patterns.

4. **SQLite for test DB**: The existing `conftest.py` uses SQLite via `mkstemp()`. This avoids PostgreSQL dependency in test environments and is fast. Models use mostly portable SQL types, so SQLite compat is maintained.

5. **One factory per model**: 16 factories in `tests/factories.py`. SubFactories and RelatedFactory for relationships (e.g., Maintenance has ManyToMany with Technician via MaintenanceTechnician).

6. **Mock external services**: MinIO storage and WeasyPrint PDF generation will be mocked at the service layer to avoid external dependencies in tests.

## Risks / Trade-offs

- **SQLite vs PostgreSQL type differences**: Some PostgreSQL-specific types (UUID, ARRAY, JSONB) may need special handling in factories. Mitigation: use TypeDecorator-compatible defaults or `sqlalchemy_utils` UUID type.
- **Factory complexity**: Deeply nested models (Ticket -> Maintenance -> Worksheet -> Photos) may create slow test setup. Mitigation: use `build()` or `build_stub()` where DB persistence isn't needed; use `create()` only for integration tests.
- **Factory scaling**: 16 factories is a lot of files if split. Mitigation: keep all factories in a single `factories.py` with clear class naming.
- **Chunked upload testing**: The upload flow involves multiple requests and MinIO interaction. Mitigation: mock the MinIO client in upload service for test isolation.
