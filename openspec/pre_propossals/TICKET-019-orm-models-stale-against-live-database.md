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

## Progress 2026-09-29 — model-side drift closed, 10 live-side defects remain

Measured with `DB_NAME=atb_drift alembic check` against a disposable database
built from `deploy/schema.sql` and stamped `0001_baseline`. Autogenerate was used
only as a *measuring instrument* on a throwaway database; no revision was
generated from it, and live was not touched.

`alembic check` reported **60 operations**. After the model corrections below it
reports **10**, and the full suite is green (360 passed, 7 xfailed).

### Closed in the models (the database was right, the models were wrong)

| Change | Live | Was declared as |
| --- | --- | --- |
| `AuditMixin.created_at/updated_at` | `timestamptz`, nullable | naive `DateTime`, `NOT NULL` |
| `AuditMixin.created_by/updated_by` | nullable | `NOT NULL` |
| `pauses` audit columns (own copy, not the mixin) | `timestamptz`, nullable | naive `DateTime`, `NOT NULL` |
| `tickets.priority` | enum `priority_type` | `String` |
| `tickets.status` | enum `status_type` | `String` |
| `tickets.ticket_date`, `maintenances.maintenance_date` | `date` | `DateTime` |
| 11 free-text columns | `text` | `String` (implicit `varchar`) |
| `token_blacklist.jti` | `uuid` | `String(36)` |
| `worksheets.pdf_path` | `varchar(100)` | `String(500)` |
| `worksheets.receiver_signature_timestamp/generated_at` | `timestamptz` | naive `DateTime` |
| `fsm_users.email/user_name/user_role` | `NOT NULL` | nullable |
| 9 `uploads_sessions` columns | `NOT NULL` | nullable |
| `technicians.user_id` | named `UNIQUE` + named index | unnamed `unique=True` + `index=True` |

Two constraints had to be *named* rather than merely present: Alembic compares
constraints and indexes by name, so an unnamed `unique=True` is reported as a
difference even when the live column is unique in the same way.

Two details worth keeping:

- The enums use `Enum(...).with_variant(String(), "sqlite")`. The live types are
  real PostgreSQL enums, but `conftest.py` builds the test schema on SQLite, and
  a native enum cannot be created there.
- `token_blacklist.jti` is `Uuid(as_uuid=False)`. The column is a genuine `uuid`
  in live, but the code keys the blacklist on the raw JWT string, so the Python
  side must keep accepting strings. `as_uuid=False` preserves the DDL type while
  letting the existing string binding work; `as_uuid=True` broke 101 tests with
  `'str' object has no attribute 'hex'`.

`tests/test_model_live_alignment.py` (52 cases) pins all of the above against
`Base.metadata` with no database, so this drift cannot silently return. Verified
to bite: reverting the audit timestamps to naive, the enum to `String`, or
`pdf_path` to `String(500)` each fails it.

### The database is wrong here — these need a live migration, not a model edit

These 10 are the *opposite* defect. Editing the models to match them would weaken
the schema, so they are deliberately left outstanding:

1. `maintenances_spares` and `maintenances_technicians` have **no primary key at
   all** in live. The models declare `PrimaryKeyConstraint`. Duplicate join rows
   are therefore possible. **`alembic check` cannot see this**: autogenerate does
   not compare primary keys, so this drift is invisible to the check that is
   supposed to catch drift. It was found by querying `pg_constraint` directly.
2. `maintenances_spares.{maintenance_id,spare_id,qty}`,
   `maintenances_technicians.{maintenance_id,technician_id,start_hour,end_hour}`
   and `pauses.maintenance_id` are nullable in live but `NOT NULL` in the models
   (8 columns). The first six are the columns of the two missing primary keys, so
   adding the keys fixes them.
3. `maintenances` carries **two** identical unique constraints on `ticket_id`,
   `maintenances_ticket_id_key` and `uq_maintenances_ticket_id`. The model
   declares one. The duplicate should be dropped in live, not modelled twice —
   declaring both would make every future database carry the redundancy.
4. `spares.unit` has foreign key `spares_unit_fkey` to `uom(unit)`, but `uom` is
   one of the 5 deliberately unmodelled tables from TICKET-018. The FK cannot be
   declared in the model without breaking `create_all` on SQLite, and it is a
   real integrity constraint worth keeping. This one needs a decision rather
   than a mechanical fix: either drop the FK in live, or extend the reserved-table
   exclusion in `app/models/reserved.py` to cover foreign keys pointing at
   reserved tables.

### Why the audit columns were made nullable rather than tightened

Live genuinely contains NULLs: **all 16 rows in `photos` have `created_by`
NULL**. The app itself produced them, because `save_photo` did not populate the
audit columns (fixed in `61510b6`). Tightening live to `NOT NULL` would fail on
existing data and would need a backfill that cannot invent the missing user. So
the models reproduce what live is, and the data-quality issue is recorded here
instead of being hidden behind a constraint the database does not actually
enforce.

## The `spares.unit` foreign key, resolved without a model edit

Of the 10 live-side items, 9 are database defects that need a migration. The tenth
was different: `spares.unit` carries a real foreign key to `uom(unit)`, but `uom`
is one of the five deliberately unmodelled tables, so the model cannot declare the
reference at all. An unresolvable reference breaks `Base.metadata.create_all`,
which is how the test suite builds its schema.

Declaring it in the model was therefore not available, and dropping the constraint
in live would have discarded referential integrity for no benefit, since nothing
writes `spares` yet. The constraint is real and should stay. The fix belongs in the
same place the original hazard was fixed: `app/models/reserved.py`, which already
tells autogenerate to skip the unmodelled tables.

`include_object` now also skips `type_ == "foreign_key_constraint"` when the
constraint *points at* a reserved table. Alembic calls the hook for foreign keys as
well as tables, and the reflected constraint exposes each reference as
`element.target_fullname` (`'uom.unit'`, or `'public.uom.unit'` when
schema-qualified), so the referenced table is the second-to-last dotted component.
The filter keys on the referenced table and never on the constraint's own name, so
an unrelated constraint merely called `holidays_fkey` stays in scope.

`DB_NAME=atb_drift alembic check` now reports **9** items rather than 10. Six guards
in `tests/test_alembic_env.py` cover the new branch, verified to bite against three
mutations: removing the branch, taking the first dotted component instead of the
second-to-last, and keying on the constraint name instead of its target.

The 9 remaining items are unchanged and still need a live migration: 8 `NOT NULL`s
on the two join tables and `pauses.maintenance_id`, and the duplicate
`maintenances_ticket_id_key` on `maintenances`. Adding the two missing primary keys
— which `alembic check` cannot see, because autogenerate never compares primary
keys — would resolve 4 of the 8.
