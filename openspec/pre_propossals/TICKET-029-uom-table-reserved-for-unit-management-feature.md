# `uom` is reserved for a unit-management feature that was never built

## Metadata

- **Summary**: the live table `uom` has no ORM model, holds 10 rows behind a
  foreign key from 575 live `spares` rows, and backs a unit-management feature
  that was designed and never built; it is kept, unmodelled, until that feature
  is actually specified
- **Issue Type**: Reserved Table
- **Project**: app-tickets-backend
- **Priority**: Medium — the only one of the five that holds data and is
  referenced, so a wrong decision here is not reversible by dropping a table
- **Labels**: database, reserved-table, schema-design, technical-debt
- **Owner**: ratara5
- **Review date**: 2027-09-30, one year out rather than the 90 days used for live
  defects. The blocking design question is a schema redesign, not a defect, and it
  belongs with whoever builds the feature. Revisit when that feature is scheduled.
- **Related**: TICKET-018 (the parent decision), TICKET-021, TICKET-024,
  TICKET-025, TICKET-026, TICKET-027, TICKET-028

## Description

`uom` is one of the five tables TICKET-018 decided to keep for future features. It
holds no ORM model, deliberately, and `app/models/reserved.py` keeps Alembic's
autogenerate from proposing to drop it.

Live structure, read on 2026-09-30 from `db_gestiket_acme`:

| Column | Type | Notes |
|---|---|---|
| `unit` | `character varying` | **primary key** — see below |
| `magnitude` | `character varying` | `volumen`, `masa`, `longitud`, `unidad` |
| `uom_description` | `text` | nullable |
| `ref_unit` | `character varying` | self-FK → `uom.unit`, `NO ACTION` |
| `factor_conversion` | `numeric(20,10)` | widened from `numeric(5,2)` by TICKET-021 |

It holds **10 rows**, and it is referenced by `spares.unit` — a modelled table with
575 live rows. It is the only reserved table that cannot be dropped: the foreign
key would block it while `spares` rows point at it.

## The primary key is the whole problem

`unit` alone is the primary key, so **one row can hold exactly one reference unit
and one factor.** Every base unit therefore stores a self-ratio
(`ref_unit = unit`, `factor = 1.0`):

```
   unit            magnitude   ref_unit   factor_conversion   spares rows
---------------   ---------   --------   -----------------   -----------
   u               unidad      u          1.0000000000        506
   m               longitud    m          1.0000000000         48
   lb              masa        lb         1.0000000000          0
   kg              masa        kg         1.0000000000          5
   l               volumen     l          1.0000000000          2
   rollo           rollo       rollo      1.0000000000          2
   cilindro        volumen     lb        40.0000000000          6
   medio cilindro  volumen     lb        20.0000000000          1
   gal             volumen     l          3.7900000000          4
   par             unidad      u          2.0000000000          1
```

That is enough for one relationship per unit, and today's data needs exactly
that: a base unit points at itself, a derived unit points at its base.

**It cannot express a unit with two relationships.** The concrete case is
`lb → kg`, factor `0.45359237`. `lb` occupies its row with the self-ratio `1.0`
— and it has to, because `cilindro` and `medio cilindro` both point at it and the
foreign key requires the row to exist. There is therefore nowhere to *also* record
`lb` against `kg`. The same applies to any future base unit that is referenced by
a derived unit: the row is consumed by its self-ratio before it can carry a real
ratio.

This is why TICKET-024's repair used a self-ratio of `1.00` rather than the more
interesting constant. It was not a choice; it was the only thing the schema
allowed.

The fix is a composite primary key on `(unit, ref_unit)`, which turns "one row per
unit" into "one row per relationship" and lets `lb` appear twice. That changes
what a `uom` row *means*, and it is a redesign, not a drift fix. TICKET-018
declined to take it unilaterally and so does this ticket.

### What the redesign would have to touch

Recorded so the cost is known before the decision, not after:

- The primary key, and `uom_ref_unit_fkey`, which must be re-pointed to the
  composite `(unit, ref_unit)`.
- **`spares.unit → uom(unit)` breaks.** This is the finding that changes the
  cost, and it was measured rather than reasoned:

  ```
  CREATE TABLE uom (unit varchar NOT NULL, ref_unit varchar,
                    factor numeric(20,10), PRIMARY KEY (unit, ref_unit));
  CREATE TABLE spares (spare_id serial PRIMARY KEY, unit varchar,
                        CONSTRAINT spares_unit_fkey
                          FOREIGN KEY (unit) REFERENCES uom(unit));
  ERROR:  there is no unique constraint matching given keys
          for referenced table "uom"
  ```

  A foreign key must target a `UNIQUE` or `PRIMARY KEY` column set, and a
  composite key on `(unit, ref_unit)` does **not** make `unit` unique — which is
  the entire point of the change. The same statement proves the change does work
  as intended: `('lb','lb',1.0)` and `('lb','kg',0.45359237)` both insert.

  So the composite key is **not** a self-contained change to `uom`. It takes
  `spares` with it, and the 575 live rows are affected after all. An earlier
  draft of this ticket claimed otherwise, on the reasoning that a single-column
  reference into the leading column of a composite key would still resolve. That
  is wrong, and the error above is the proof.
- A new Alembic migration, plus `deploy/schema.sql` regenerated (never
  hand-edited).
- The seed loader. `etl/seed_db.sh` disables constraint triggers with
  `SET session_replication_role = 'replica'` (TICKET-020), which is how the table
  came to hold rows violating a validated constraint in the first place. A
  composite key widens the window for that defect.
- `app/models/reserved.py` and the Alembic foreign-key exclusion hook, which
  currently suppress exactly these two foreign keys from autogenerate.

### The shape that does work, and needs no change to `spares`

If the feature is ever built, **splitting the table is the design that survives**,
and it was verified end to end on a disposable database:

```sql
CREATE TABLE uom_units (            -- the thing spares points at
  unit        varchar PRIMARY KEY,
  magnitude   varchar,
  description text
);
CREATE TABLE uom_conversions (      -- one row per relationship
  unit     varchar NOT NULL REFERENCES uom_units(unit),
  ref_unit varchar NOT NULL REFERENCES uom_units(unit),
  factor   numeric(20,10) NOT NULL,
  PRIMARY KEY (unit, ref_unit)
);
-- spares keeps its existing single-column FK, now to uom_units(unit)
```

Measured on that schema:

- `lb` holds **two** rows at once — `lb -> lb = 1.0000000000` and
  `lb -> kg = 0.4535923700` — which is exactly the case the current table cannot
  represent.
- `spares.unit` still works, and a bogus unit is still rejected:
  `Key (unit)=(NO_SUCH) is not present in table "uom_units"`.

`uom_units(unit)` is a single-column primary key, so `spares.unit` has a valid
foreign-key target and **the 575 rows need no data migration**. The current 10
rows map across by inserting each unit once and then each self-ratio as a
conversion.

The cost is a migration rather than a constraint tweak, and it turns one reserved
table into two. That is a real trade, and it belongs to whoever builds the
feature. It is recorded here because it is the answer to the question this ticket
raises, and the composite key is not.

### Two further traps

- **`magnitude` is a free-text vocabulary in Spanish, in an English-language
  schema**, and nothing constrains it. `par` is `unidad` (count), `rollo` is
  `rollo` (its own name, in neither language), and `medio cilindro` is `volumen`.
  Whether `magnitude` is a category or a dimension is not stated, and the values
  do not distinguish the two.
- **`ref_unit` is nullable but the self-ratio convention makes it never empty.**
  A row with `ref_unit IS NULL` is representable and would break any conversion
  walk that follows `ref_unit` until it stops. Whether `NULL` is a valid base unit
  or a hole needs deciding before the key changes.

## Why no model was written

Per TICKET-018: a speculative model for an unbuilt feature is contradicted by the
real one, and a model in the codebase is far harder to remove than a table in a
script. Here the model would have to encode a primary key that is known to be
wrong, and would be the artefact that makes it expensive to change.

## What must be decided when the feature is built

1. **Composite primary key on `(unit, ref_unit)`, or the split into `uom_units` +
   `uom_conversions`.** This is the blocking question; the rest is detail. The
   split is the verified option and the only one that leaves `spares.unit` alone;
   the composite key is cheaper to write and does not survive contact with
   `spares_unit_fkey`.
2. `magnitude`: category, dimension, or a lookup table. A lookup table is the
   answer that supports `magnitude` being constrained, and it would add a sixth
   reserved table until then.
3. Whether `ref_unit` may be `NULL`, and whether a base unit is a self-ratio or an
   absence of one. The current data uses self-ratios, so a change here alters
   every existing row.
4. Whether `magnitude` groups must agree across a conversion — that `masa` can
   only convert to `masa`. Nothing enforces it, and the redesign is the moment to.

## Scope boundary

- No model. No migration. No change to the live database. No `DROP`.
- No composite-key redesign, and no split. TICKET-021's widening is already
  applied; what remains is the key. The live primary key is still
  `PRIMARY KEY (unit)` and this ticket changes nothing about it.

## Acceptance criteria

- [x] The table has a ticket of its own, satisfying TICKET-018's per-table
      requirement. This is that ticket; it records no code change.
- [x] The single-relationship limitation is stated with the concrete blocked case
      (`lb → kg`), so the redesign is justified by a real requirement rather than
      by tidiness.
- [x] The cost of the redesign is enumerated, **including the finding that the
      obvious composite primary key breaks `spares_unit_fkey`** and cannot be
      applied on its own, and that the split design avoids that while needing no
      data migration for the 575 `spares` rows. Both verified on a disposable
      database rather than argued.
- [ ] The feature is specified, and this ticket closes with it.
