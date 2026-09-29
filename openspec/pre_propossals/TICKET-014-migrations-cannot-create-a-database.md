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

## Resolution

**Partly resolved 2026-09-27, and deliberately not "fixed" in migrations.**

The premise of this ticket is right and the conclusion has changed. Migrations
should not create a database, and they do not: `alembic upgrade head` is now a
verified no-op on a correctly stamped database, and a new database is built by
loading `deploy/schema.sql` and then `alembic stamp head`. Database creation
stays an admin action, because `postgres-gci` is shared and the app must not hold
the credentials to create one.

What is resolved: there is now a reproducible path from empty to current —
`deploy/schema.sql`, a dump of the live database, verified to build all 23 tables
on a stock PostgreSQL 16 with only `pg_uuidv7` added.

What is deliberately not provided: a migration that creates the database, because
that is the arrangement the two-plane doctrine forbids.

The reported absence of a baseline revision is also resolved: `0001_baseline`
exists and is the anchor. See `docs/deployment-guide.md` §2.2.2.
