# Bug: the ORM models are stale against the live database, so init.sql cannot be regenerated from them

## Metadata

- **Summary**: the SQLAlchemy models disagree with the live database badly enough that `alembic check` reports 94 pending operations (37 type changes, 52 nullability changes, 2 sequence changes, 3 removals), so regenerating a schema from them would produce a valid script for the wrong schema
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, schema-drift, deployment
- **Owner**: ratara5
- **Review date**: 2026-12-27, aligned with `TICKET-018`

## Description

`docs/deployment-guide.md` §2.2 and `docs/learned-lessons.md` both record the
conclusion that **"the models win; the other artifact is a liability until it is
regenerated or retired."** That conclusion is only half true, and the half that is
wrong is the dangerous one.

The models are not a faithful description of the live database. They are a third
artifact that has drifted in both directions. Regenerating `init.sql` from them
would produce a script that runs cleanly and creates the wrong schema — which is
strictly more dangerous than the loud failures `init.sql` has today.

This ticket exists because it is the **blocker** for retiring `init.sql`. It was
found while closing `TICKET-017`, where regenerating was the obvious fix and was
rejected on this evidence.

## Measured evidence

`Base.metadata.create_all` compiled against the PostgreSQL dialect, no database
required, compared against the live database read via `pg_attribute`:

| Object | Live database | Models generate | Consequence of regenerating |
|---|---|---|---|
| `tickets.ticket_id` | `integer`, **no default** | `SERIAL` | adds a sequence to a column whose ids are assigned by the external ticketing system |
| `tickets.priority` | `priority_type` (native enum, in use) | `VARCHAR` | silently discards a live enum type |
| `tickets.status` | `status_type` (native enum, in use) | `VARCHAR` | silently discards a live enum type |
| `tickets.created_at` | `timestamp with time zone` | `timestamp without time zone` | timezone is lost on every audit column |
| `photos.photo_id` | `text` (12 rows: `330cbdb1`, `b69794e3`, …) | `SERIAL` integer | changes a text primary key that holds live data |
| `token_blacklist.jti` | `uuid` | `VARCHAR(36)` | reverts applied migration `7f4d68531ba6` |
| `maintenances.maintenance_id` | `uuid DEFAULT uuid_generate_v7()` | `uuid`, no default | the model default is Python-side, so the ETL loses its write path |
| `uploads_sessions.upload_id` | `uuid DEFAULT uuid_generate_v7()` | `uuid`, no default | same |
| `tickets.created_by` / `updated_by` | **nullable** | `nullable=False` | adds 7 NOT NULL constraints that do not exist |
| `spares.unit` | foreign key onto `uom(unit)`, validated | **no foreign key** (`master.py:30` says so in a comment) | a freshly built database would have no constraint here at all |

The last row matters twice over. The live database enforces a constraint the models
do not describe, so a database built from the models is missing it — and
`TICKET-020` shows the one existing violation of it went unnoticed because the seed
loader disables constraint triggers.

Both enum types are confirmed live and in use, not abandoned:

```
    typname     | typtype | columns_using_it
------------------+---------+------------------
 priority_type    | e       |                1
 status_type      | e       |                1
```

And `photos.photo_id` really does hold short hex strings in a `text` column, so
the `SERIAL` change is not cosmetic.

## The "it works, so the models are right" inference is false

The application runs correctly against this database, which is exactly why this
drift has survived. It is tempting to conclude that a working application proves
its models describe its database. It does not. The clearest counterexample is in
this repository: `token_blacklist.jti` is `uuid` in the live, working database and
`String(36)` in the model — the application is running against a column its own
model misdescribes, right now. `photos.photo_id` is the same story with 12 rows
behind it.

A working application is evidence that the *columns it uses* are compatible. It is
not evidence that the models describe the schema.

## Why this must be fixed before regeneration, not after

The failure modes differ in kind, which is the whole argument:

- `init.sql` today fails **loudly**: the `VARCHAR → SERIAL` foreign key on
  `tickets` is refused on every image (`TICKET-008`), and `pg_uuidv7` is missing on
  stock PostgreSQL (`TICKET-007`).
- A regenerated file would fail **silently**, because `create_all` emits valid SQL
  for a schema that is subtly wrong. A `SERIAL` on `tickets.ticket_id` is not a
  syntax error; it is a wrong id assigned to a real ticket in a real database.

Converting a loud, immediate, well-understood failure into a quiet, deferred,
data-corrupting one is a regression. Regeneration is the right end state, but only
after the models are corrected and a check exists that the two agree.

## Acceptance criteria

- [ ] Each row of the table above is reconciled: either the model is corrected to
      the live type, or the live column is deliberately changed and the change is
      migrated. The decision is recorded per row, not applied silently.
- [ ] `tickets.ticket_id` is explicitly documented as externally assigned, with a
      test or comment preventing a `SERIAL`/`autoincrement` from being reintroduced.
- [ ] `priority_type` and `status_type` are modelled as `sa.Enum` with those exact
      type names, so the types are emitted and reused rather than replaced.
- [ ] The models declare `server_default` for `uuid_generate_v7()` on the columns
      that have it in the live database, so the ETL write path survives a rebuild.
- [x] `alembic/env.py` imports every model module, so `target_metadata` reports
      all 17 model tables. Done 2026-09-27: measured against a database built from
      `deploy/schema.sql`, the old two-table metadata made autogenerate emit
      `remove_table` for 20 of the 23 live tables.
- [x] The 5 tables that have no models are excluded by a named, tested
      `include_object` hook rather than by the absence of a model. Done
      2026-09-27, kept for future features per TICKET-018. Verified against a
      disposable database: 5 `remove_table` before the hook, 0 after.
- [ ] `alembic check` reports no operations against a disposable database. Still
      open, and blocked by the two heads (`TICKET-009`), which make autogenerate
      refuse to run at all: "Target database is not up to date".
- [ ] The baseline revision is derived from `deploy/schema.sql`, the same dump that
      serves as the dev bootstrap, so the two cannot disagree.
- [ ] The `NOT NULL` divergence on the audit columns is resolved in one direction
      and applied to both the models and the database.

## Notes

- Blocking ordering, and it changed on 2026-09-27. This ticket used to block
  regeneration of `init.sql`. It no longer does: `init.sql` is retired and deleted,
  and `deploy/schema.sql` is generated from the live database, which is correct
  regardless of the models. `TICKET-017` is closed on that basis.
  This ticket is now open for two reasons of its own: the models still disagree with
  the database, so any query written through them can be wrong; and
  `alembic/env.py` exposes only 2 tables, so autogenerate is actively dangerous and
  the baseline cannot be written yet.
- `docs/learned-lessons.md` §5 asserted "the models win". That was too strong and is
  corrected here: the database is the ground truth, and the models are a claim about
  it. The corrected statement is in `deploy/schema.sql`'s header and in
  `ai-specs/skills/deploying-backend-vps/SKILL.md`.
- The `photos.maintenance_id` Integer-vs-`Uuid` drift is a **previous** instance of
  exactly this failure, already recorded in `docs/learned-lessons.md` §4 and fixed
  by migration `0004`. It is the precedent: the model was not updated to match the
  migration, and the mismatch surfaced later as an upload bug. The models must
  mirror the database, not the other way round.
- Read-only inspection. `postgres-gci` was started and returned to `exited`;
  `minio-acme` was not touched.
