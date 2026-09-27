# Bug: init.sql depends on a non-standard extension that only the shared custom image provides

## Metadata

- **Summary**: `init.sql` requires `pg_uuidv7`, which stock PostgreSQL does not ship, so a deployment on a new server silently loads as almost empty
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment
- **Status note**: revised 2026-09-26. An earlier version of this ticket claimed the extension is unavailable on the shared server. That was wrong; the measured facts are below.

## Description

`init.sql:13` runs `CREATE EXTENSION IF NOT EXISTS pg_uuidv7;`. That extension is a
third-party module, not part of PostgreSQL. Whether it exists depends entirely on the
**server image**:

| Server image | `pg_uuidv7` |
|---|---|
| `postgres:16` (stock) | absent — the statement fails |
| `infrastructure-companies-postgres-gci` (the shared container's image) | **present**, 1.7, PostgreSQL 16.13 |

Verified on the shared image:

```bash
docker run --rm --entrypoint sh infrastructure-companies-postgres-gci -c \
  'ls $(pg_config --sharedir)/extension/ | grep -i uuid'
# pg_uuidv7--1.7.sql
# pg_uuidv7.control
```

So the existing shared database was built on a server that has it. The defect is that
**this requirement is undocumented and unguarded**: nothing in the repository records
that the schema depends on a custom image, so a server built from the stock image
fails at line 13.

`psql` continues after an error unless told to stop, so the script "finishes" and the
operator sees a database that exists. On a stock server only 1 of the 21 declared
tables gets created before dependent statements start failing.

**Impact:** a first deployment on any new VPS built from the stock image produces a
corrupt schema that presents as a successful load. Detected late, when a feature reads
a table that was never created.

## Reproduction

```bash
docker run -d --name probe -e POSTGRES_PASSWORD=x postgres:16
docker exec probe psql -U postgres -c "CREATE DATABASE d"
docker exec -i probe psql -U postgres -d d < init.sql 2>&1 | grep ERROR
docker exec probe psql -U postgres -d d -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
```

Observed on stock: `ERROR: extension "pg_uuidv7" is not available`, cascading errors,
and `1` table present instead of 21.

## Acceptance criteria

- The repository records the image requirement next to the schema (runbook and/or
  `init.sql` header comment): the schema needs `pg_uuidv7`, and either the custom
  image is used or the extension is installed explicitly.
- A guard exists so a server lacking the extension fails loudly before any DDL runs,
  rather than after the first statement.
- Every `psql` invocation in any script or runbook uses `-v ON_ERROR_STOP=1`.

## Notes

- The application itself does not need the extension: UUIDv7 primary keys are generated
  in Python (`default=uuid7` in `app/models/maintenance.py` and `app/models/upload.py`,
  from the `uuid6` package). Only the SQL script needs it. That is why the app can run
  against a server where the script would fail — and why the failure stays hidden.
- `init.sql:138` and `init.sql:310` also use `uuid_generate_v7()` as a column default,
  so removing the statement requires replacing those defaults.
- This ticket is independent of `TICKET-008` (the impossible foreign key), which breaks
  the script on **both** images.
- Interim procedure: build the schema from the SQLAlchemy models instead; see
  `docs/deployment-guide.md` §2.2.
