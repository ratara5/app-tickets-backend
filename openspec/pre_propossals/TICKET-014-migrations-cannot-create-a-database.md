# Bug: the migrations cannot create a database, so there is no reproducible path from empty to current

## Metadata

- **Summary**: every Alembic revision is a delta that assumes the base tables exist, so a fresh database cannot be built with `alembic upgrade head`
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment

## Description

The repository contains three different attempts to describe the schema, and none of
them can build a database from empty:

| Source | Result on an empty database |
|---|---|
| `init.sql` | fails: impossible foreign key (`TICKET-008`), and needs `pg_uuidv7` (`TICKET-007`) |
| `alembic upgrade head` | fails: the first revision is a delta, not a base schema |
| SQLAlchemy models (`create_all`) | works, but leaves the migration history empty and the graph inconsistent |

The first migration is a delta, so it fails on the empty tables it expects to alter:

```
ERROR:  relation "maintenances_technicians" does not exist
```

The graph also has two heads (`TICKET-009`), so even the plural form is ambiguous, and
two revision ids exceed the history table's own column width (`TICKET-010`).

The only working procedure today is an undocumented manual one: create the tables from
the models, hand-create `alembic_version` at `VARCHAR(64)`, then `alembic stamp heads`.
That procedure lives in prose in `docs/deployment-guide.md` §2.2 and is executed by
hand.

**Impact:** every new environment, every new developer and every disaster recovery
depends on an operator following prose correctly. The failure mode is silent: stamping
a schema that does not match the models produces a database that serves requests and
fails later, in a feature, on data.

## Reproduction

```bash
docker run -d --name probe -e POSTGRES_PASSWORD=x postgres:16
docker exec probe psql -U postgres -c "CREATE DATABASE d"
python -m alembic upgrade head          # with DATABASE_URL pointed at d
# → relation "..." does not exist, or "Multiple head revisions are present"
```

## Acceptance criteria

- A single documented command builds an empty database to the current schema and leaves
  the migration history consistent, with the migration tool reporting a no-op upgrade
  afterwards.
- That command is exercised by a test against a disposable database, so it cannot rot
  silently.
- The procedure is captured in a script or an openspec change, not only in prose.

## Notes

- Related: `TICKET-007`, `TICKET-008`, `TICKET-009`, `TICKET-010`, and
  `TICKET-015` (the live database's history is stale relative to its own contents).
- `TICKET-011` is unrelated: it concerns the presigned-URL TTL unit.
