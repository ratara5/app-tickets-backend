# Development Guide

This guide provides step-by-step instructions for setting up the development environment and running tests for the Field Service Management (FSM) API backend.

## Prerequisites

Ensure you have the following installed:
- **Python 3.12+**
- **Docker** and **Docker Compose**
- **Git**
- **pip** (Python package manager)

## Quick Start

```bash
# 1. Clone and enter project
git clone <repo-url> app-tickets-backend
cd app-tickets-backend

# 2. Start PostgreSQL (Docker)
docker compose up -d postgres

# 3. Create the schema from deploy/schema.sql (see docs/deployment-guide.md §2.2)
#    The DATABASE must already exist; this creates the TABLES.
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres \
    -d db_gestiket_acme < deploy/schema.sql
# Expected: 23 tables. Do NOT build the schema from the models -- they are stale
# against the live database: alembic check reports 94 pending operations (37 type changes, 52 nullability changes, 2 sequence changes, 3 removals) (TICKET-019).

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Start development server
uvicorn app.main:app --reload --reload-dir app
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## Detailed Setup

### 1. Environment Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
# Edit .env with your local configuration
```

Required environment variables in `.env`:

```bash
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=db_gestiket_acme

# MinIO (optional for development)
# TWO origins, because the backend and the phone live on different sides.
#
# MINIO_ENDPOINT: where the BACKEND dials the store. Host run -> 127.0.0.1.
# In Docker -> minio-acme. Never a LAN address: a DHCP lease in this variable
# takes photo uploads down when the lease moves (post-mortem 2026-09-29).
MINIO_ENDPOINT=127.0.0.1
MINIO_PORT=9000
#
# MINIO_PUBLIC_ENDPOINT: the origin baked into every presigned photo_url, i.e.
# what the emulator or device must resolve. The signature covers the Host
# header, so this is fixed at signing time and the URL is never rewritten
# afterwards. Use the machine LAN address for a stopgap, and a DHCP reservation
# or a domain for anything longer lived. Emulator note: the stock Android
# emulator also reaches the host at 10.0.2.2, but a physical device cannot, so
# prefer a reservation that both can resolve.
MINIO_PUBLIC_ENDPOINT=192.168.10.30
MINIO_REGION=us-east-1
MINIO_ACCESS_KEY=<your-key>
MINIO_SECRET_KEY=<your-secret>
MINIO_DEFAULT_BUCKET=company-uploads
BASE_OBJECT_PATH="Maintenances/Correctivos"
EXT_BY_TYPE={"image/jpeg":".jpg","image/png":".png","application/pdf":".pdf"}
ALLOWED_TYPES=["image/jpeg","image/png","application/pdf"]
PRESIGNED_TTL=1  # HOURS, not seconds (see TICKET-011)


# JWT
JWT_SECRET=<your-secret>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=15

# Company Settings
COUNTRY=CO
TZ_COMPANY=America/Bogota
CONTRACTOR_NAME="Your Company S.A.S"
CONTRACTOR_NIT="123456789-0"
CLIENT_COMPANY_NAME=CLIENT
CLIENT_FORMAT_NAME=FUS

# Templates & PDF
TEMPLATES_DIR=app/templates/reports
PDF_SUFFIX=Soporte
```

### 2. Start Dependencies

```bash
# Start PostgreSQL
docker compose up -d postgres

# Verify it's running
docker compose ps
```

### 3. Initialize Database

Create the schema from [`deploy/schema.sql`](../deploy/schema.sql), a
`pg_dump --schema-only` snapshot of the live database. It gives you 23 tables, the
two enum types, the `pg_uuidv7` extension, and the 5 reserved tables for unbuilt
features.

`init.sql` is **retired and deleted**. It declared a foreign key from `VARCHAR` onto a
`SERIAL` key, which PostgreSQL refuses; because `psql` continued past the error, the
load reported success while every table after that line was skipped (`TICKET-008`). It
also needed `pg_uuidv7`, absent from stock `postgres:16` (`TICKET-007`), and omitted
`token_blacklist`, which every authenticated request queries (`TICKET-017`).

```bash
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres \
    -d db_gestiket_acme < deploy/schema.sql
```

`-v ON_ERROR_STOP=1` is mandatory. Without it `psql` reports errors, continues, and
exits 0, so a failed load looks like a successful one.

Do **not** build the schema from the SQLAlchemy models with `create_all`. Measured
against the live database on 2026-09-27, the models are stale in nine structural
places, so `create_all` produces a clean, wrong schema and nothing reports it
(`TICKET-019`). The database is the ground truth; the models are a claim about it.

Do **not** create `alembic_version` by hand or run `alembic stamp heads` yet. The
history has two heads (`TICKET-009`), no revision creates the base tables
(`TICKET-014`), and two revision ids exceed `VARCHAR(32)` (`TICKET-010`). A stamped
incomplete graph makes `alembic heads` look healthy while no migration can actually
repair the database. The baseline revision is derived from the same dump.

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Key packages:
- `fastapi==0.124.4` — Web framework
- `sqlalchemy==2.0.40` — ORM
- `psycopg2-binary==2.9.10` — PostgreSQL driver
- `alembic==1.15.2` — Migrations
- `jose[cryptography]==3.5.0` — JWT tokens
- `passlib[bcrypt]==1.7.4` — Password hashing
- `uvicorn[standard]==0.34.0` — ASGI server
- `pydantic-settings==2.9.1` — Settings management
- `structlog==25.5.0` — Structured logging
- `minio==7.2.7` — S3-compatible storage client

### 5. Start Development Server

```bash
uvicorn app.main:app --reload --reload-dir app
```

The API will be available at:
- **API**: `http://localhost:8000`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## Testing

### Prerequisites
Test dependencies are included in `requirements.txt`. Ensure they're installed:

```bash
pip install -r requirements.txt
```

Key test packages:
- `pytest==8.2.1` — Test runner
- `pytest-asyncio==0.24.0` — Async test support
- `httpx==0.27.0` — HTTP client for endpoint testing
- `factory_boy==3.3.0` — Test data factories
- `pytest-mock==3.14.0` — Mocking utilities
- `pytest-cov==5.0.0` — Coverage reporting

### Running Tests

```bash
# Run all tests with verbose output
pytest -v

# Run all tests and generate coverage report
pytest --cov=app --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/test_ticket_service.py -v

# Run tests matching keyword
pytest -k "ticket"

# Stop on first failure
pytest -x

# Run last failed tests only
pytest --last-failed
```

### Test Configuration

Tests use:
- **pytest** as the test runner
- **httpx.AsyncClient** with FastAPI's `TestClient`
- **factory_boy** for test data factories
- **pytest-mock** for mocking
- **pytest-cov** for coverage reporting

Coverage threshold: **80%** minimum.

### Writing Tests

Create test files in the `tests/` directory following naming convention `test_*.py`:

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
class TestTickets:
    async def test_list_tickets_returns_200(self, client):
        response = await client.get("/tickets")
        assert response.status_code == 200
```

## Database Migrations (Alembic)

```bash
# Create a new migration (auto-detect changes)
alembic revision --autogenerate -m "description_of_change"

# Apply pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

## Linting and Type Checking

```bash
# Lint check
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format code
ruff format .

# Type check
mypy app
```

## API Documentation

The API specification is exported manually:

```bash
# Start the server
uvicorn app.main:app --reload --reload-dir app

# Export OpenAPI spec
curl http://localhost:8000/openapi.json -o docs/api-spec.json
```

The canonical API contract lives in:
- `docs/api-spec.json` — Machine-readable OpenAPI spec
- `docs/api-spec.yml` — YAML version of the same spec

Both backend and the separate React Native frontend project consume this spec.

## Full Stack with Docker

```bash
# Start all services (API + PostgreSQL)
docker compose up --build

# View logs
docker compose logs -f api

# Stop all services
docker compose down

# Stop and remove volumes (reset DB)
docker compose down -v
```

## Common Tasks

```bash
# Generate PDF worksheet
# (triggered via API endpoint, uses WeasyPrint + Jinja2 templates)

# Upload file with chunking
# (POST /uploads with multipart chunks, reassembled server-side)

# Export OpenAPI spec to docs/
curl http://localhost:8000/openapi.json -o docs/api-spec.json

# Create new SQLAlchemy model
# 1. Create app/models/<name>.py
# 2. Create app/schemas/<name>.py
# 3. Create app/repositories/<name>_repo.py
# 4. Create app/services/<name>_service.py
# 5. Create app/api/routes/<name>.py
# 6. Register router in app/api/routes/__init__.py
# 7. Do NOT hand-edit any schema file. deploy/schema.sql is GENERATED: regenerate it
#    from the live database with the command in its own header, after the migration
#    has been applied. A hand edit is invisible until someone regenerates it.
#    If the table is a placeholder for a feature you are not building, do not write a
#    model: file a ticket like TICKET-018, so the discrepancy is documented instead
#    of invisible.
# 8. Generate Alembic migration
# 9. Write tests
```

## Project Conventions

- **Python**: 3.12+, type hints required on all functions
- **Code style**: ruff (compatible with Black + isort)
- **Testing**: pytest with factory_boy data factories
- **Migrations**: Alembic auto-generated, reviewed before apply
- **API contract**: OpenAPI 3.1 via FastAPI, exported to `docs/`
- **Frontend**: React Native (separate project, communicates via this API)
