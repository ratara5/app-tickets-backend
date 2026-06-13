---
description: Backend development standards, best practices, and conventions for the FastAPI/Python/SQLAlchemy application including Domain-Driven Design, SOLID principles, architecture patterns, API design, and testing practices
globs: ["app/**/*.py", "app/core/**/*.py", "app/models/**/*.py", "app/schemas/**/*.py", "app/repositories/**/*.py", "app/services/**/*.py", "app/api/**/*.py", "tests/**/*.py"]
alwaysApply: true
---

# Backend Project Standards and Best Practices

## Table of Contents

- [Overview](#overview)
- [Technology Stack](#technology-stack)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Domain-Driven Design Principles](#domain-driven-design-principles)
- [SOLID and DRY Principles](#solid-and-dry-principles)
- [Coding Standards](#coding-standards)
- [API Design Standards](#api-design-standards)
- [Database Patterns](#database-patterns)
- [Testing Standards](#testing-standards)
- [Performance Best Practices](#performance-best-practices)
- [Security Best Practices](#security-best-practices)
- [Development Workflow](#development-workflow)
- [Deployment](#deployment)

---

## Overview

This document outlines best practices, conventions, and standards for the Field Service Management (FSM) backend application. The backend follows Domain-Driven Design (DDD) principles with a layered architecture using FastAPI, SQLAlchemy, and PostgreSQL.

## Technology Stack

### Core Technologies
- **Python 3.12+**: Runtime environment
- **FastAPI**: Web framework with automatic OpenAPI docs, async support, and Pydantic validation
- **SQLAlchemy 2.0**: ORM with declarative mapping
- **Alembic**: Database migration management
- **Pydantic v2**: Data validation via BaseModel/Settings

### Database & Storage
- **PostgreSQL 16**: Relational database
- **MinIO**: S3-compatible object storage for files/photos
- **WeasyPrint**: PDF generation from HTML/CSS templates

### Authentication
- **JWT** (python-jose): Stateless token-based auth
- **passlib + bcrypt**: Password hashing

### Testing Framework
- **pytest**: Test runner with fixtures and plugins
- **httpx (AsyncClient)**: Native FastAPI TestClient with async support
- **pytest-cov**: Coverage reporting (target: 80%+)
- **factory_boy**: Declarative test data factories
- **pytest-mock**: Mocking utilities
- **testcontainers** (optional): Spin up real PostgreSQL in CI

### Development Tools
- **ruff**: Code linting and formatting
- **mypy**: Static type checking
- **uvicorn**: ASGI server (development)
- **gunicorn + uvicorn workers**: Production server

## Architecture Overview

### Domain-Driven Design (DDD)

The backend follows a layered DDD architecture with domain-centric organization:

- **Presentation Layer** (`app/api/`) — FastAPI route handlers, request parsing, response formatting, auth via `Depends(get_current_user)`
- **Application Layer** (`app/services/`, `app/schemas/`) — Business logic orchestration, Pydantic schemas for validation/serialization
- **Domain Layer** (`app/models/`, `app/repositories/`) — SQLAlchemy models, repository interfaces + implementations, business rules, AuditMixin
- **Infrastructure Layer** (`app/core/`) — DB engine, JWT handling, MinIO client, PDF generation, structlog, pydantic-settings

## Project Structure

```
app/
├── main.py                    # FastAPI app creation, entry point for uvicorn
├── server.py                  # create_app() factory
├── api/
│   ├── deps.py                # Dependency injection (get_current_user, get_db)
│   └── routes/
│       ├── __init__.py        # Router aggregation
│       ├── auth.py            # Authentication endpoints
│       ├── tickets.py         # Ticket CRUD endpoints
│       ├── maintenances.py    # Maintenance endpoints
│       ├── users.py           # User management
│       ├── uploads.py         # File upload endpoints
│       └── worksheets.py      # PDF worksheet endpoints
├── core/
│   ├── config.py              # (reserved for extra configuration)
│   ├── database.py            # Engine, SessionLocal, get_db
│   ├── logger.py              # structlog setup
│   ├── security.py            # JWT encode/decode
│   ├── settings.py            # Pydantic Settings from .env
│   ├── storage.py             # MinIO client
│   └── utils/                 # Shared utility functions
├── models/
│   ├── base.py                # SQLAlchemy declarative base
│   ├── audit_mixin.py         # created_at/updated_at/created_by/updated_by
│   ├── registry.py            # Auto-discovery model registry
│   ├── fsm_user.py            # User & Technician models
│   ├── ticket.py              # Ticket & AddWkd models
│   ├── maintenance.py         # Maintenance, MaintenanceTechnician, MaintenanceSpare
│   ├── master.py              # Market, Equipment, Spare, Uom, Labsdl
│   ├── cancellation.py        # Cancellation
│   ├── photo.py               # Photo
│   ├── pause.py               # Pause
│   ├── upload.py              # UploadSession
│   └── worksheet.py           # Worksheet
├── schemas/
│   ├── auth.py                # Login request/response
│   ├── user.py                # User schemas (CurrentUser, etc.)
│   ├── ticket.py              # Ticket request/response
│   ├── maintenance.py         # Maintenance request/response
│   ├── cancellation.py        # Cancellation schemas
│   ├── pause.py               # Pause schemas
│   ├── file.py                # File/photo schemas
│   ├── upload.py              # Chunked upload schemas
│   └── worksheet.py           # Worksheet schemas
├── repositories/
│   ├── ticket_repo.py         # Ticket data access
│   ├── maintenance_repo.py    # Maintenance data access
│   ├── fsm_user_repo.py       # User data access
│   ├── cancellation_repo.py   # Cancellation data access
│   ├── pause_repo.py          # Pause data access
│   ├── photo_repo.py          # Photo data access
│   ├── upload_repo.py         # Upload session data access
│   └── worksheet_repo.py      # Worksheet data access
├── services/
│   ├── registry.py            # Service auto-discovery
│   ├── auth_service.py        # Authentication logic
│   ├── ticket_service.py      # Ticket business logic
│   ├── maintenance_service.py # Maintenance business logic
│   ├── cancellation_service.py# Cancellation business logic
│   ├── pause_service.py       # Pause business logic
│   ├── photo_service.py       # Photo business logic
│   ├── upload_service.py      # Chunked upload logic
│   └── worksheet_service.py   # Worksheet/PDF generation logic
└── templates/
    ├── reports/               # Jinja2 PDF templates
    └── others/
```

## Domain-Driven Design Principles

### Entities

Entities have a distinct identity that persists over time. In this project they use SQLAlchemy with an `_id` primary key and `AuditMixin`.

```python
class Ticket(Base, AuditMixin):
    __tablename__ = "tickets"

    ticket_id = Column(Integer, primary_key=True)
    ticket_date = Column(DateTime)
    ticket_description = Column(String)
    priority = Column(String)
    status = Column(String)
```

**Best Practice**: Encapsulate business logic in domain methods on the entity, not in services.

### Value Objects

Join-table records like `MaintenanceTechnician` and `MaintenanceSpare` use compound primary keys — they are composite value objects:

```python
class MaintenanceTechnician(Base, AuditMixin):
    __tablename__ = "maintenances_technicians"
    __table_args__ = (PrimaryKeyConstraint("maintenance_id", "technician_id"),)

    maintenance_id = Column(Uuid, ForeignKey("maintenances.maintenance_id"))
    technician_id = Column(Integer, ForeignKey("technicians.technician_id"))
    start_hour = Column(Time)
    end_hour = Column(Time)
```

### Aggregates

The `Ticket` aggregate root contains `Maintenance`, which in turn contains `Pause`, `Photo`, `MaintenanceTechnician`, `MaintenanceSpare`, and `Worksheet`.

### Repositories

Repositories abstract data access behind a class. Each aggregate has a corresponding repository:

```python
class TicketRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, ticket_id: int) -> Ticket | None:
        return self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()

    def save(self, ticket: Ticket) -> Ticket:
        self.db.add(ticket)
        self.db.flush()
        return ticket
```

### AuditMixin

All transactional tables include `AuditMixin` providing:
- `created_at` (server default `NOW()`)
- `updated_at` (auto-updated on update)
- `created_by` / `updated_by` (FK to `fsm_users`)
- `creator` / `updater` relationships

## SOLID and DRY Principles

### Single Responsibility Principle (SRP)
- Models declare structure + domain logic
- Repositories handle data access
- Services orchestrate business logic
- Routes handle HTTP concerns
- Schemas handle serialization/validation

### Dependency Inversion Principle (DIP)
Services depend on repository abstractions injected via constructor:

```python
class TicketService:
    def __init__(self, repo: TicketRepository):
        self.repo = repo

@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    service = TicketService(TicketRepository(db))
    return service.get_ticket(ticket_id)
```

### DRY
- Abstract common DB logic into `AuditMixin`
- Use `registry.py` for model auto-discovery
- Centralize validation in Pydantic schemas
- Reuse service logic across endpoints

## Coding Standards

### Naming Conventions
- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase` (e.g., `TicketService`, `AuditMixin`)
- **Constants**: `UPPER_SNAKE_CASE`
- **Files/Modules**: `snake_case.py`
- **DB Tables/Columns**: `snake_case`

```python
# Good
class TicketRepository:
    def find_by_id(self, ticket_id: int) -> Ticket | None: ...
```

### Python Type Hints
- All function signatures MUST include type annotations
- Use `|` union syntax (Python 3.10+): `str | None` not `Optional[str]`
- Use `list[X]` not `List[X]` (Python 3.9+)
- Return types always declared

```python
def get_ticket(self, ticket_id: int) -> Ticket | None:
    return self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
```

### Imports
Order: stdlib → third-party → local. Use absolute imports within `app` package.

```python
from uuid6 import uuid7

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.audit_mixin import AuditMixin
```

### Error Handling
- Use FastAPI `HTTPException` with descriptive messages
- Create custom exception classes for domain errors
- Use global exception handlers for consistent error format

```python
from fastapi import HTTPException

class NotFoundError(HTTPException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail)

class UnauthorizedError(HTTPException):
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(status_code=401, detail=detail)
```

### Logging
Use `structlog` with context (user ID, ticket ID, correlation ID):

```python
from app.core.logger import get_logger

logger = get_logger(__name__)
logger.info("ticket_created", ticket_id=ticket.ticket_id, user_id=current_user.user_id)
```

### Validation
- Input validation via Pydantic schemas at the API boundary
- Business rule validation in services
- DB constraints as final safety net

## API Design Standards

### REST Endpoints

```python
GET    /tickets          # List tickets (filterable)
GET    /tickets/{id}     # Get ticket by ID
POST   /tickets          # Create ticket
PATCH  /tickets/{id}     # Update ticket
DELETE /tickets/{id}     # Delete ticket

GET    /maintenances/{id}       # Get maintenance
POST   /maintenances            # Create maintenance
PATCH  /maintenances/{id}       # Update maintenance

POST   /auth/login              # User login -> JWT token
GET    /users/me                # Current user profile

POST   /tickets/{id}/cancel    # Cancel ticket
GET    /tickets/{id}/pauses    # Get pauses for ticket
```

### Request/Response Patterns
- All responses use JSON
- Proper HTTP status codes (200, 201, 204, 400, 401, 403, 404, 422, 500)
- Pagination for list endpoints (`limit`/`offset`)

```python
@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    service = TicketService(TicketRepository(db))
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket
```

### Authentication
- JWT Bearer tokens via `Authorization: Bearer <token>` header
- Obtain via `POST /auth/login` with email + password
- Protected endpoints use `Depends(get_current_user)`
- Token expiry via `JWT_EXPIRE_MINUTES`

### OpenAPI Documentation
- FastAPI auto-generates OpenAPI 3.1 from route definitions
- Visit `/docs` (Swagger UI) or `/openapi.json`
- Export for client consumption:

```bash
curl http://localhost:8000/openapi.json -o docs/api-spec.json
```

## Database Patterns

### SQLAlchemy Models
- Use `declarative_base()` from `app.models.base`
- Apply `AuditMixin` to all transactional tables
- Explicit `__tablename__` matching PostgreSQL table names
- Explicit `ForeignKey` constraints
- Define `relationship()` for related model navigation

### Alembic Migrations
- All schema changes through Alembic migrations
- Never modify database manually in production

```bash
alembic revision --autogenerate -m "add_ticket_priority_index"
alembic upgrade head
```

### Repository Pattern

```python
class TicketRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_by_id(self, ticket_id: int) -> Ticket | None:
        return (
            self.db.query(Ticket)
            .options(joinedload(Ticket.market), joinedload(Ticket.equipment))
            .filter(Ticket.ticket_id == ticket_id)
            .first()
        )
```

### Query Optimization
- Use `joinedload` / `selectinload` to avoid N+1 queries
- Index frequently filtered columns
- Use `with_entities()` for read-only queries
- Batch operations within transactions

## Testing Standards

### Framework: pytest

- Test files: `tests/test_*.py`
- Use `httpx.AsyncClient` with FastAPI `TestClient` for endpoint testing
- Use `factory_boy` for test data factories
- Coverage target: **80%+**

### Test Structure

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
class TestTicketService:
    async def test_get_ticket_returns_ticket_when_found(self, client):
        ticket_id = 1
        response = await client.get(f"/tickets/{ticket_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["ticket_id"] == ticket_id
```

### Categories Required for Each Feature
1. **Happy Path** — valid inputs, expected outputs
2. **Error Handling** — invalid inputs, missing data, auth failures
3. **Edge Cases** — boundary values, empty data, nulls
4. **Validation** — Pydantic schema, business rules
5. **Integration** — DB operations, external services

### Test Fixtures

```python
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
```

### Mocking
- Mock external services (MinIO, external APIs) at the repository boundary
- Use `pytest-mock` (`mocker` fixture)
- Prefer test doubles over mocks for domain logic

### Coverage Configuration

```ini
# pyproject.toml
[tool.coverage.run]
source = ["app"]
omit = ["app/tests/*"]

[tool.coverage.report]
fail_under = 80
```

### Running Tests

```bash
pytest -v                          # Verbose output
pytest --cov=app --cov-report=term-missing   # Coverage
pytest -k "test_ticket"           # Specific tests
pytest -x                          # Stop on first failure
```

## Performance Best Practices

### Database
- Index foreign keys and frequently queried columns
- Use `selectinload` for related collections
- Use `TIMESTAMPTZ` for timezone-aware timestamps
- Prefer server-side defaults (e.g., `func.now()`) over client-side

### Application
- Use FastAPI async endpoints for I/O-bound operations
- Use MinIO presigned URLs for file downloads (don't proxy through the API)
- Cache repeated expensive computations
- Use background tasks for PDF generation

### API
- Paginate list endpoints (`limit`/`offset`)
- Use Pydantic's `model_dump(exclude_unset=True)` for partial updates
- Set timeouts for external service calls

## Security Best Practices

### Authentication
- All protected endpoints use `Depends(get_current_user)`
- JWT tokens: minimal claims (`sub`, `exp`, `iat`)
- Passwords hashed with bcrypt via passlib
- Configurable token expiry

### Authorization
- Validate resource ownership before mutations
- Role-based access: `admin`, `technician`, viewer

### Input Validation
- All request bodies validated by Pydantic
- SQL injection prevented by SQLAlchemy parameterized queries
- File uploads validated by content type and size (via `ALLOWED_TYPES` setting)
- Path traversal prevented by sanitized MinIO paths

### Secrets Management
- Never commit `.env` files or secrets
- All secrets in environment variables via `pydantic-settings`
- Validate required vars at startup in `settings.py`

## Development Workflow

### Git Workflow
- **Feature Branches**: `feature/[short-description]`
- **Commit Messages**: Descriptive English, imperative mood
  - `feat: add ticket cancellation endpoint`
  - `fix: handle null assigned_to in ticket query`
  - `refactor: extract PDF generation to service`
- **Code Review**: Before merging to main
- **Small Branches**: Keep branches small and focused

### Development Scripts

```bash
uvicorn app.main:app --reload     # Hot reload
alembic upgrade head               # Apply migrations
alembic revision --autogenerate -m "desc"  # Create migration
pytest -v                          # Run tests
pytest --cov=app                   # Coverage
ruff check .                       # Lint
ruff format .                      # Format
mypy app                           # Type check
```

### Code Quality Gates
- [ ] All tests pass (`pytest -v`)
- [ ] Coverage >= 80%
- [ ] No lint errors (`ruff check .`)
- [ ] No type errors (`mypy app`)
- [ ] Code formatted (`ruff format .`)

## Deployment

### Docker

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    depends_on: [postgres]
  postgres:
    image: postgres:16
```

### Production Server

```bash
gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 4 \
    --bind 0.0.0.0:8000
```

### Environment Variables

Configured via `.env` and loaded by `pydantic-settings` in `app/core/settings.py`. All settings are validated at startup.
