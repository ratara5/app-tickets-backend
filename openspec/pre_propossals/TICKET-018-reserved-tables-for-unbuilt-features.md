# Decision: five tables in the live database have no model and no built feature

## Metadata

- **Summary**: `hollidays`, `materials`, `preliquidated`, `services` and `uom` exist in the live database and in `init.sql`, have no ORM model, and back features that were never built
- **Issue Type**: Decision required
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: database, schema-drift, technical-debt
- **Owner**: **ratara5** (repository maintainer and sole committer — no other owner was specified, so this is assigned to the only accountable identity in `git log`)
- **Review date**: **2026-12-27** (90 days from filing). If no decision is recorded by then, this escalates rather than lapsing.
- **Decision options**: build the feature, redesign the table, or drop it after backup and approval
- **Decision**: **Keep all five for future features** (ratara5, 2026-09-27). None is to be dropped, and none is to be modelled until its feature is actually built. The consequence is that Alembic must be told to skip them, which is now implemented — see "What was done instead" below.
- **Second decision, 2026-09-30**: of the three ways to close the last open acceptance criterion, **file one ticket per table** (criterion 3) rather than redesigning `uom`'s primary key or renaming `hollidays`. The latter two are schema changes belonging to the features that will justify them; `TICKET-029` and `TICKET-025` record them with their costs enumerated so the choice is available later without re-deriving it. **This ticket is closed.**

## Description

Five tables are declared in `init.sql` and exist in the live database, but no ORM
model declares them. They are artifacts of features that were designed and then
not built. They are not inert: they are in the schema a new developer reads.

The real cost is not the empty tables. It is that **a future developer reads the
live schema, assumes `uom` is a real feature, and builds against columns that will
be redesigned when the feature is actually written.** The trap is the assumption,
not the table.

## Measured state

Read-only inspection of the live database `db_gestiket_acme` on 2026-09-27
(`reltuples` was `-1` for every one of these tables, meaning never analyzed and
therefore uninformative, so exact counts were taken instead):

| Table | Rows | Referenced by | Risk |
|---|---|---|---|
| `uom` | **9** | `spares.unit` foreign key | **highest** — holds data and is referenced |
| `hollidays` | 0 | nothing | name is misspelled, see below |
| `materials` | 0 | nothing | |
| `preliquidated` | 0 | nothing | |
| `services` | 0 | nothing | |

Only `uom` is load-bearing: it holds 9 rows and `spares.unit` has a foreign key onto
it. **Dropping `uom` would fail while `spares` rows reference it**, and `spares`
holds 575 rows. The other four are empty and unreferenced, but "empty" is a
statement about today, not a permission to `DROP`.

### `uom`'s referential integrity is already broken

The foreign key exists and is fully enforced — it is *not* a dormant constraint:

```
   child_table |      conname      |                definition
---------------+--------------------+----------------------------------------------
 uom           | uom_ref_unit_fkey  | FOREIGN KEY (ref_unit) REFERENCES uom(unit)
 spares        | spares_unit_fkey   | FOREIGN KEY (unit) REFERENCES uom(unit)

 conname           | convalidated | confdeltype
-------------------+--------------+--------------
 uom_ref_unit_fkey | t            | a   (NO ACTION)
 spares_unit_fkey  | t            | a   (NO ACTION)
```

`convalidated = t` means PostgreSQL verified existing rows when the constraint was
added, and `NO ACTION` blocks both the delete and the update that would orphan a
child. Yet the data contradicts it. All 575 `spares` rows have a non-null `unit`,
and exactly one of them points at nothing:

| `uom` row | `spares` rows using it |
|---|---|
| `u` | 506 |
| `m` | 48 |
| `cilindro` | 6 |
| `kg` | 5 |
| `gal` | 4 |
| `l` | 2 |
| `rollo` | 2 |
| `par` | 1 |
| `medio cilidndro` | **0** |

The last row is a **typo** — `medio cilidndro`, with the letters transposed — and
nothing references it. Meanwhile one `spares` row references `medio cilindro`,
spelled correctly, which **does not exist in `uom` at all**.

A validated, `NO ACTION` foreign key cannot produce that state on its own. The
mechanism is in this repository: `etl/seed_db.sh:99` runs the seed `COPY` inside
`SET session_replication_role = 'replica'`, which disables constraint triggers for
the duration of the load. Referential integrity is switched off by design during
seeding and never re-checked afterwards. This is filed separately as `TICKET-020`.

The practical consequence for this decision: **`uom` has never had its integrity
validated, and the only reason it is not obviously broken is that the loader cannot
report a violation.** A redesign must reconcile 575 referencing rows, one of which
is already orphaned, and the misspelled `medio cilidndro` row is either the intended
unit or a typo to be dropped — nobody currently knows which.

### Two name traps

- The table is **`hollidays`**, with a double L, in both `init.sql` and the live
  database. It is not `holidays`. Any ticket, query or rename that assumes the
  correct spelling will not find it.
- `init.sql` also has a self-referencing foreign key on `uom` (`ref_unit → uom.unit`),
  and a `materials.spare_id` comment reading `to be reset`, which is a note to a
  future self that the column was never settled.

## Why no model was written

Deliberately not done, and this ticket records the reasoning so it is not
"helpfully" undone:

- Writing speculative ORM models for unbuilt features produces columns that get
  **contradicted** by the real feature when it is written, and a model in the
  codebase is much harder to remove than a table in a script. The spec gets
  written twice, and the wrong one wins by default.
- Deleting the tables is premature. Four are empty, but `uom` holds 9 rows behind a
  foreign key from 575 `spares` rows, and none of them has been backed up.

## What was done instead, so the discrepancy is not invisible

1. `deploy/schema.sql` carries all five tables, because it is a dump of the live
   database and they exist there. It is **generated and must not be hand-edited**,
   so the `!! RESERVED` comments that were in `init.sql` are deliberately absent:
   a hand-added comment would be silently destroyed by the next regeneration, which
   is worse than no comment, because it looks maintained. This ticket, with the
   owner and review date, is the record instead.
2. `tests/test_deploy_assets.py` carries a **named** allow-list, `RESERVED_TABLES`,
   and `test_schema_sql_covers_every_table_the_models_require` asserts that all five
   are present in the dump, that the total is 23, and that no model table is
   missing. The allow-list is visible in the test itself rather than hidden in a
   fixture, so adding a sixth table requires a deliberate, reviewable edit.

   The named-comment form (`RESERVED_TABLES_WITHOUT_MODELS`, one line of reason per
   table) was in `tests/test_init_sql_schema.py`, deleted with `init.sql`; its
   one-line reasons are preserved in this ticket.

Net effect: a documented discrepancy with an expiry is a plan; an undocumented one
is a trap.

## Acceptance criteria

- [x] A decision is recorded for each of the five tables: **keep for future features** (ratara5, 2026-09-27). No drop, no model until the feature is built.
- [x] Nothing is dropped, so no backup or drop approval is required. This also removes the `spares.unit` blocker: `uom` stays, so the foreign key stays valid.
- [x] The `medio cilindro` / `medio cilidndro` discrepancy is resolved: the spare row
      pointing at a non-existent unit is corrected or the unit is created, and the
      typo'd row is confirmed as intended or dropped. Until then `uom` is known to be
      inconsistent. Keeping the table does not fix its contents, and this is tracked
      with the loader defect in `TICKET-020`.
- [x] Each of the five gets a ticket of its own for the feature it is reserved for.
      Filed 2026-09-30: `TICKET-025` (`hollidays`), `TICKET-026` (`materials`),
      `TICKET-027` (`preliquidated`), `TICKET-028` (`services`), `TICKET-029`
      (`uom`). Filenames and findings only — no model, no migration, no change to
      the live database, and no `DROP`.
- [x] The exclusion is enforced where it matters, not only recorded. `app/models/reserved.py`
      declares the five by name and supplies Alembic's `include_object` hook, wired
      into both the offline and the online path in `alembic/env.py`. Verified against
      a disposable database built from `deploy/schema.sql`: 5 `remove_table` before
      the hook, 0 after. `tests/test_alembic_env.py` guards the list against the dump
      and the imports against `app/models/`.
- [~] If `hollidays` is renamed, the misspelling is fixed in the live database, in
      a migration, in `deploy/schema.sql` (by regeneration), in this ticket and in
      `app/models/reserved.py`, in one change. Until then the exclusion list must
      keep the double L, or autogenerate would stop protecting the real table.

      **Not chosen on 2026-09-30, deferred rather than closed.** The second
      sentence is the requirement in force today and it holds:
      `app/models/reserved.py` keeps the double L, and
      `tests/test_alembic_env.py` guards the list against the dump, so a
      misspelling introduced there would fail a test rather than silently stop
      protecting the table. The rename is tracked in `TICKET-025` with the
      feature that would justify it — which is also the feature most likely to
      decide the table is dropped instead, which would make the rename moot.

## Notes

- Read-only inspection only. `postgres-gci` was started for the query and returned
  to `exited`; `minio-acme` was left untouched. No data was written.
- The `!! RESERVED` comments in `init.sql` are not a substitute for this ticket —
  they cannot be reviewed, assigned or dated by a process.
- Related: `TICKET-017` (the `token_blacklist` gap, the mirror image of this one: a
  modelled table missing from the script), `TICKET-019` (the models are stale
  against the live database, which is why regeneration is blocked).

## Resolved and closed 2026-09-30

The decision this ticket records — keep the five tables, exclude them from
Alembic's metadata — is implemented and holding. `app/models/reserved.py` names
them, `alembic/env.py` routes both `context.configure` calls through
`include_object`, and 52 metadata guards plus 6 FK-exclusion guards pin the
behaviour.

### Closed here

**The `medio cilidndro` discrepancy.** Resolved in TICKET-024. The spare row was
right and the `uom` key was wrong — the row's own `uom_description` already read
`medios cilindros`, which makes the description the source of truth for the
intended value. `UPDATE uom SET unit='medio cilindro'` fixed it, and adding the
missing `lb` base unit repaired both foreign keys that the rows were violating.
The typo existed only in live data; `etl/data/` holds just `.gitkeep`, so no
source can reintroduce it.

**Foreign keys into `uom` are excluded from autogenerate.** `spares.unit ->
uom.unit` and `uom.ref_unit -> uom.unit` would otherwise make every autogenerate
report changes it could not act on, because there is no `uom` model to compare
them against. `include_object` now returns False for any foreign key whose target
is a reserved table.

### Deferred, not fixed, and now carried by TICKET-029

**One row per unit.** `uom.unit` is the primary key, so a unit can hold exactly
one reference unit and one factor. That is enough for today's data — a base unit
is a self-ratio, a derived unit points at its base — but it cannot express a unit
with two relationships. The lb -> kg constant `0.45359237` that motivated
TICKET-021's widening is exactly such a case: `lb` is already referenced by
`cilindro` and `medio cilindro`, so it has a row, so there is nowhere to also
record it against `kg`.

This was found while repairing TICKET-024, and it is why the repair used a
self-ratio of `1.00` rather than the more interesting constant. Expressing both
needs a composite primary key on `(unit, ref_unit)`, which is a schema change
that alters what a `uom` row means and is a decision for whoever builds the unit
  management feature — not a drift fix, and not taken unilaterally.

Still true, and deliberately not acted on: the `uom` redesign was one of the
three options weighed on 2026-09-30 and was not chosen. It is now `TICKET-029`.
That ticket verified the obvious answer on a disposable database and found it
does not work: a composite primary key on `(unit, ref_unit)` **breaks**
`spares_unit_fkey`, because a foreign key must target a `UNIQUE` or `PRIMARY KEY`
column set and a composite key does not make `unit` unique. The shape that does
work is a split into `uom_units` + `uom_conversions`, also verified, which leaves
`spares` untouched and needs no data migration for its 575 rows. Both results are
recorded there so the feature does not have to re-derive them.


### Closed here: the per-table tickets

**Per-table tickets and the `hollidays` rename.** The five tickets are now filed,
so this ticket's remaining acceptance criteria are met and it closes. What each
one records, briefly, because the findings were worth more than the filing:

- `TICKET-025` (`hollidays`): the application **already has** holiday support and
  does not use this table — `get_holidays` in `app/core/utils/dates.py` resolves
  from the `holidays` Python package, which handles per-country and movable
  holidays that a single `title` column keyed by `date` cannot. The honest
  expectation when the feature is written is that the table is dropped, not
  modelled.
- `TICKET-026` (`materials`) and `TICKET-028` (`services`): column for column
  these are one unfinished design. Both carry a `ticket_id` with **no foreign
  key** while `maintenance_id` is properly constrained, and both declare `qty`
  and `price` as bare nullable `numeric` — the same money-scale trap as
  `TICKET-021`. The one-ticket-per-table split is a filing convenience, not a
  description of the work.
- `TICKET-027` (`preliquidated`): a marker table whose only problem is that
  "pre-liquidated" is defined nowhere. Structurally the soundest of the five —
  its primary key is a real enforced foreign key into a modelled table.
- `TICKET-029` (`uom`): the single-relationship limitation, with the concrete
  blocked case recorded — `lb → kg` cannot be expressed because `lb`'s row is
  consumed by the self-ratio that `cilindro` and `medio cilindro` require. It
  also records a correction worth having made before the feature is written: the
  obvious fix, a composite primary key on `(unit, ref_unit)`, **breaks**
  `spares_unit_fkey`, verified on a disposable database. The split into
  `uom_units` + `uom_conversions` is the shape that works, and it leaves `spares`
  alone.

**The `hollidays` rename was not chosen.** It remains open, tracked as
criterion 6 above, and still belongs with the feature that would justify it —
renaming a table for a spelling, while no feature uses it, changes the exclusion
list that is currently the only thing protecting it.
