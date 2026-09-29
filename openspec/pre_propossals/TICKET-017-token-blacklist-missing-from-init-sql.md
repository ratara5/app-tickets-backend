# Bug: init.sql omits token_blacklist, so a database built from it 500s on every authenticated route

## Metadata

- **Summary**: `token_blacklist` is absent from `init.sql`; the application queries it on every authenticated request, so a database bootstrapped from the file fails open on a missing table
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment, schema-drift
- **Status**: **Resolved** 2026-09-27. `init.sql` is retired and deleted; its replacement is `deploy/schema.sql`, a `pg_dump --schema-only` snapshot of the live database, which contains `token_blacklist` with the live column types. The stopgap patch described below was the interim measure and has been superseded — see "Resolution" at the end.

## Description

`token_blacklist` is load-bearing backend code, not a leftover:

| Call site | Operation |
|---|---|
| `app/api/deps.py:25` | `is_blacklisted()` on **every** authenticated request |
| `app/services/auth_service.py:29` | `add_to_blacklist()` on logout |

The table exists in the ORM model (`app/models/token_blacklist.py`) and in two
migrations, `0001_add_token_blacklist` and `7f4d68531ba6_change_data_type_jti`,
but it was **absent from `init.sql`**. A database created from `init.sql` therefore
starts, the application connects, login succeeds, and then every login-protected
route raises because the table does not exist.

The live database has the table, so **the running application is not broken and
there is no outage**. The defect is latent and only bites a new database.

## Measured confirmation

Read-only comparison of the three schema artifacts:

| Artifact | Tables | Has `token_blacklist` |
|---|---|---|
| ORM models | 17 | yes |
| `init.sql` | 21 | **no** |
| live database | 23 | yes |

`17 + 5 + alembic_version = 23`, so the live database is the union of the models
and `init.sql`; the 5 extra are the reserved tables tracked by `TICKET-018`.

## Reproduction

```bash
docker run -d --name probe -e POSTGRES_PASSWORD=x infrastructure-companies-postgres-gci
docker exec probe psql -U postgres -c "CREATE DATABASE d"
docker exec -i probe psql -v ON_ERROR_STOP=1 -U postgres -d d < init.sql
docker exec probe psql -U postgres -d d -tAc \
  "SELECT to_regclass('public.token_blacklist')"     # empty -> the table is missing
```

Then any authenticated request fails with
`psycopg2.errors.UndefinedTable: relation "token_blacklist" does not exist`.

## Severity

Latent, not an outage, and the window is narrow but real. `init.sql` is no longer
the documented bootstrap path — `docs/deployment-guide.md` §2.2 builds the schema
from the models instead — **but the file is still the first thing a developer
finds and runs.** `README.md` §SETUP routes to `bootstrap.sh --init-file init.sql`,
and `bootstrap.sh:108` runs `psql` **without** `-v ON_ERROR_STOP=1` and then prints
`✓ init.sql executed` regardless of what happened. So the trap is reachable from the
top of the README, and the script that runs it cannot fail loudly. (`bootstrap.sh`
is itself broken in a different way — `TICKET-016`.)

## Resolution applied

`token_blacklist` is now declared in `init.sql` under a new `SESSION / AUTH`
section, **matching the live database rather than the ORM model**:

```sql
CREATE TABLE IF NOT EXISTS token_blacklist (
    jti UUID PRIMARY KEY,
    expires_at TIMESTAMP NOT NULL
);
```

The model declares `jti` as `String(36)`, but migration `7f4d68531ba6` altered the
column to `uuid` and that migration is applied on the live database. Confirmed
read-only against the live column:

```
 jti        | uuid                        | not null
 expires_at | timestamp without time zone | not null
```

Copying the model's `VARCHAR(36)` would have introduced a **third** divergent
value. `0001` creates the `String(36)` primary key and `7f4d68531ba6` converts the
type, so the live end state is `uuid` — which is what the file now records.

### Why not regenerate

Regenerating `init.sql` from the models was evaluated and rejected. The models are
not a trustworthy generation source today: measured against the live database they
are stale in at least six places, and `Base.metadata.create_all` would introduce
`SERIAL` primary keys on externally assigned ids, drop two live native enums, drop
`TIMESTAMPTZ`, revert an applied migration, and remove the server-side
`uuid_generate_v7()` defaults the ETL writes through. The details and the full
measurement are in `TICKET-019`.

This matters for how the defect would have surfaced. `init.sql`'s known faults are
**loud**: the `VARCHAR → SERIAL` foreign key at the `tickets` table fails on every
image (`TICKET-008`), and the `pg_uuidv7` extension fails on stock PostgreSQL
(`TICKET-007`). A regenerated file's faults would be **silent**, because
`create_all` emits valid SQL for a schema that is subtly the wrong shape. Trading a
loud failure for a quiet one is a regression, not a fix.

**The patch in this ticket is therefore a stopgap.** It closes the 500s and nothing
more. It does not make `init.sql` safe to run: `TICKET-007` and `TICKET-008` still
apply, and `bootstrap.sh` still cannot report failure.

## Acceptance criteria

- [x] `token_blacklist` is declared in the schema artifact with the live column
      types (`jti uuid` primary key, `expires_at timestamp NOT NULL`).
- [x] A test fails if `token_blacklist` is ever removed from the schema again.
- [x] A test fails if `token_blacklist.jti` is ever written as `VARCHAR`, which
      would revert migration `7f4d68531ba6`.
- [x] The schema artifact declares itself generated, with its provenance, so
      nobody reads it as hand-maintained.
- [x] `bootstrap.sh` runs `psql` with `-v ON_ERROR_STOP=1` and reports failure.
- [x] `bootstrap.sh` defaults to the generated schema instead of the retired file,
      and verifies afterwards that `token_blacklist` exists.
- [x] The retired `init.sql` is deleted, so it cannot be reached by accident.

## Regression guards

`tests/test_deploy_assets.py` — no database required, runs in CI. These replaced
the guards in `tests/test_init_sql_schema.py`, which were deleted together with
`init.sql`, because testing a retired artifact gives false assurance.

| Test | Guards |
|---|---|
| `test_schema_sql_contains_token_blacklist_with_the_live_column_types` | the table cannot disappear, and cannot be reverted to `VARCHAR(36)` |
| `test_schema_sql_covers_every_table_the_models_require` | the whole class, not just this table |
| `test_bootstrap_does_not_default_to_the_retired_init_sql` | the retired file cannot be reached by accident |
| `test_bootstrap_schema_load_cannot_report_false_success` | `psql` cannot exit 0 after an error |
| `test_bootstrap_verifies_the_load_instead_of_asserting_it` | a load that omits the table is reported as failure |

Each was verified by mutation: reintroducing the defect makes the corresponding test
fail.

## Notes

- Verified the patch by parsing `init.sql` and comparing against `pg_attribute` on
  the live database. It was **not** verified by executing the script, because the
  script cannot be executed end to end while `TICKET-008` stands, and loading it
  would write to the shared container.
- `bootstrap.sh:45` runs `source .env`, which `TICKET-013` shows is unsafe.
- Restored `postgres-gci` to `exited` after the read-only inspection.

## Resolution (2026-09-27)

The stopgap is superseded. `init.sql` is **retired and deleted**, and the schema
artifact is now [`deploy/schema.sql`](../../../deploy/schema.sql), a
`pg_dump --schema-only --no-owner --no-privileges` snapshot of the live database.

Three properties make this the correct answer rather than a third hand-maintained
copy:

- **It cannot be wrong, only stale.** The database is the ground truth about the
  database. The models are stale in 94 measured places (`TICKET-019`), so a
  generated-from-models script would load cleanly and build the wrong schema.
- **One dump, two outputs.** The dev bootstrap and the future Alembic baseline are
  derived from the same snapshot, so they cannot disagree.
- **It is labelled.** The header records the source, the exact command, and the
  commit. `tests/test_deploy_assets.py` fails if that header is removed, so the file
  cannot be mistaken for hand-maintained.

`bootstrap.sh` now defaults to it, passes `-v ON_ERROR_STOP=1`, and verifies that
`token_blacklist` exists after the load instead of asserting success.

`TICKET-019` is no longer a blocker for this ticket. It remains open for a different
reason: the ORM models still disagree with the database, and `alembic/env.py` still
exposes only 2 tables, so autogenerate is unsafe and the baseline is not yet written.
