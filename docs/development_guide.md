# Development Guide

This guide provides step-by-step instructions for setting up the development environment and running tests for the Field Service Management (FSM) API backend.

## Prerequisites

Ensure you have the following installed:
- **Python 3.12+**
- **Docker** and **Docker Compose**
- **Git**
- **pip** (Python package manager)

## Run locally

Two commands. Every step between them is written down below; there is no
undocumented step in this path.

```bash
make setup-local    # bring up: create, provision, migrate, seed, start, print endpoints
make gate-local     # prove it: authenticate, read, write, upload, verify, clean up
```

`make setup-local` is idempotent — run it again after a `git pull`, after a
reboot, or after the shared core restarts. `make local-down` stops only this
project's API container and detaches this project from the shared core's
network; it never stops the core.

Before the first run, and only the first run:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
```

And `.env` must carry the local keys documented in `.env.example`:
`CORE_COMPOSE_COMMAND`, the core's admin credentials under
`CORE_DB_ADMIN_*` / `CORE_MINIO_ROOT_*`, and the seed account under
`SEED_USER_*`. `setup-local` stops and names the missing key rather than
guessing a value.

### The shared core is a precondition, not a step

This project does not start the shared PostgreSQL and MinIO. They are started
by the project that owns them, and `make setup-local` refuses to run if they are
not up. See "Not self-contained" below for what that means and why.

### This is not a staging environment

The local stack exercises the API's own code paths against a real database and a
real object store. It deliberately does **not** exercise: TLS or the reverse
proxy; the estate network topology or its external network declarations; the VPS
compose file; real mobile clients; or any behaviour that depends on a
production-shaped dataset. The seeded rows are synthetic and exist to make
writes and foreign keys work — they are not a fixture set that reproduces
production. Treat `make gate-local` as "the local environment is coherent and
the main flows work", never as "this build is releasable". Release gates live in
`docs/deployment-guide.md`.

### The reload watcher is scoped to `app/`

`make run` and `make run-native` both pass `--reload-dir app`, which makes
`uvicorn` watch `app/` and nothing else.

This is not a preference. With the watcher left at the repository root, the
number of watched files scales with the number of installed packages, so an
ordinary `pip install` into `venv/` can push the process past the inotify watch
limit. The failure then surfaces on the *next* reload — minutes after the
install that caused it — as an `ENOSPC`-style watch error with no visible
connection to what the developer just did. The same applies to the editor's own
watcher, which is why `.vscode/settings.json` excludes `venv/`,
`.pytest_cache/` and `.coverage/` from `files.watcherExclude`.

### Blast radius

Files shared between development and the VPS, and the decision taken for each.
Anything marked "no edit" is covered by a guard test that must keep passing.

| File | Shared with | Decision |
| --- | --- | --- |
| `Dockerfile` | VPS build (`infra/vps/docker-compose.yml`) | **Edited.** Added `USER`, removed dev tooling. Risk and rollback recorded in `tasks.md` §5. |
| `requirements.txt` | both image stages, VPS runtime | **Split.** `requirements-dev.txt` added; the runtime image stops installing test packages. Risk: the `migrate` stage must keep `alembic`. |
| `app/core/settings.py` | every process in every environment | **Edited.** Environment-varying defaults removed. Risk: a deployed `.env` missing a key now aborts at boot instead of defaulting. Rollback: restore the defaults. |
| `.env.example` | template for both environments | **Edited.** Local section documented. It is a template; a deployed `.env` is a copy, so no deployed value changed. |
| `Makefile` | development only | **Edited.** `--reload-dir app` plus the local targets. |
| `infra/schema.sql` | VPS `docs/deployment-guide.md` §2.2 and the local schema | **No edit.** Guard test asserts it still loads cleanly for both. |
| `infra/provision/001-create-application-roles.sql` | VPS §2.1 and the local role | **No edit.** Local provisioning reuses it with substituted placeholders, so local holds the same least-privilege role. |
| `alembic/` | VPS `migrate` job | **No edit.** |
| `tests/test_deploy_assets.py`, `tests/test_provisioning.py`, `tests/test_skill_agnosticism.py` | read `Dockerfile`, `infra/vps/` and skill prose | **No edit.** New sibling assertions were added; all must keep passing. |
| `infra/vps/**`, `docs/deployment-guide.md`, root `docker-compose.yml`, `bootstrap.sh`, `core/**`, `etl/**` | deployed environment / other projects | **No edit.** |

`docs/api-spec.yml`, `docs/api-spec.json` and `docs/data-model.md` are
unchanged: this change adds no endpoint and changes no schema. The local
compose file is new and additive.

### Which file is authoritative for the local topology

`infra/local/docker-compose.yml` is authoritative for local runs. It is the
declaration the local stack actually uses.

`core/compose.yml` in this repository is **not** authoritative for anything. It
is a copy that has drifted from the compose file it was forked from in the
sibling project, and it is not what the running containers were created from. A
developer who reads it and concludes that MinIO does not exist, or that the
database has a different configuration, is wrong — MinIO and the reverse proxy
are declared in *other* projects' compose files. This note exists because the
drifted copy is easy to find and actively misleading; the fix is to ignore it,
not to reconcile it here.

### How the topology was inventoried

The procedure, stated so it can be repeated: search every file in this
repository that declares a container, network, port or volume, then search the
sibling project that owns the shared core; for each dependency found, confirm
against the container engine which declaration actually created the running
container. A dependency that is not found in the tree is *located*, not assumed
absent — absence from this repository is not evidence of absence from the
estate. Estate deployment names and host addresses belong in
`docs/deployment-guide.md` and are deliberately not duplicated into this guide.

### Stopped containers still own their ports

This host can hold stopped containers that own ports, volumes and networks for
infrastructure that other projects declare and own. **A stopped container is not
a free port.** Under the shared-core design this no longer drives local port
selection — the core's published ports are used as they are — but it is the
reason a developer's machine can hold infrastructure this project neither owns
nor declared, and the reason bring-up must never restart it to "make room".

### Changing a shared dependency's declaration

Before changing any file that declares the shared core, establish which project
owns it. Ask the container engine which compose project created the running
container — do not assume the nearest file in this repository is the one in use.
The standing procedure is
`ai-specs/skills/dev-environment-parity/SKILL.md` §"Establish what is actually
live"; follow it there rather than a second copy of the rule kept here, which
would drift.

### Not self-contained

The local environment is **not** self-contained. It requires the shared core, and
the data it creates is *this project's* data on a shared instance other projects
also use — not a disposable private copy. Anything you drop, you recreate for
yourself; you cannot drop the core.

Safe to drop and recreate, because they belong to this project alone: this
project's database, its application role, its bucket, and its credentials.

Never to be dropped, altered or restarted for this project's benefit: the
shared core's database server, its roles, its buckets, its configuration
files, or the other projects' data on it.

### The isolation rule

Your database, your role, your bucket, your credentials. Never another
project's — and never a change to a shared configuration file to make your own
work. If your work seems to need one of those, the design is wrong, not the
rule.

## Quick Start

> Superseded for local work by [Run locally](#run-locally) above. This section
> is retained as written and is listed as stale prose in `tasks.md` §11.4; it
> predates the local stack and still describes hand-provisioning against the
> core by hand.

```bash
# 1. Clone and enter project
git clone <repo-url> app-tickets-backend
cd app-tickets-backend

# 2. Start PostgreSQL (Docker)
docker compose up -d postgres

# 3. Create the schema from infra/schema.sql (see docs/deployment-guide.md §2.2)
#    The DATABASE must already exist; this creates the TABLES.
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres \
    -d db_gestiket_acme < infra/schema.sql
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
PRESIGNED_TTL_HOURS=1  # unit is in the name; PRESIGNED_TTL still accepted


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

Create the schema from [`infra/schema.sql`](../infra/schema.sql), a
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
    -d db_gestiket_acme < infra/schema.sql
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
# 7. Do NOT hand-edit any schema file. infra/schema.sql is GENERATED: regenerate it
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

## Deferred Work

### Master data bulk load routes (deferred)
Routes for loading master/reference data in bulk have been deferred (not implemented). Planned scope:
- POST /admin/master-data/upload (multipart CSV) — validate against allowlists, dry-run/report, atomic load with rollback; authZ: admin/director
- GET /admin/master-data/templates/{entity} — download Spanish CSV templates
- POST /admin/master-data/import-preview and POST /admin/master-data/import-commit (two-step)

Constraints: header order enforced; FK validation; numeric fidelity; uom self-reference ordering. Business values fixed per entity. Spanish locale.

### PDF template management (deferred)
Routes for managing worksheet/PDF templates have been deferred:
- GET/POST/PUT/DELETE /admin/pdf-templates
- GET /admin/pdf-templates/{id}/preview

Fields: name, locale (es), sections/fields, business values fixed (branding, numbering, signatures), storage (MinIO or repo), versioning.

