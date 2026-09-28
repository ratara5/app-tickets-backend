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

- [ ] A decision is recorded for each of the five tables: build, redesign, or drop.
- [ ] For any table to be dropped: a backup is taken and the drop is approved
      explicitly. `uom` additionally requires resolving the `spares.unit`
      reference first.
- [ ] The `medio cilindro` / `medio cilidndro` discrepancy is resolved: the spare row
      pointing at a non-existent unit is corrected or the unit is created, and the
      typo'd row is confirmed as intended or dropped. Until then `uom` is known to be
      inconsistent.
- [ ] If a table is kept for a future feature, the feature gets a ticket of its own
      and this ticket closes.
- [ ] `RESERVED_TABLES` in `tests/test_deploy_assets.py` is updated to match the
      decision, and the suite stays green.
- [ ] If `hollidays` is renamed, the misspelling is fixed in the live database, in
      a migration, in `deploy/schema.sql` (by regeneration), and in this ticket, in
      one change.

## Notes

- Read-only inspection only. `postgres-gci` was started for the query and returned
  to `exited`; `minio-acme` was left untouched. No data was written.
- The `!! RESERVED` comments in `init.sql` are not a substitute for this ticket —
  they cannot be reviewed, assigned or dated by a process.
- Related: `TICKET-017` (the `token_blacklist` gap, the mirror image of this one: a
  modelled table missing from the script), `TICKET-019` (the models are stale
  against the live database, which is why regeneration is blocked).
