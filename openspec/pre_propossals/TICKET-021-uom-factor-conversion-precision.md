# TICKET-021: `uom.factor_conversion` cannot represent real conversion factors

- **Status:** Open
- **Severity:** High — silent data corruption on every conversion
- **Owner:** ratara5
- **Review by:** 2026-12-27
- **Related:** `TICKET-019`, `TICKET-020`, `TICKET-018`

## Problem

`deploy/schema.sql` declares:

    uom.factor_conversion numeric(5,2)

`numeric(5,2)` holds at most **9.99** with two decimal places. Every real
unit-conversion factor in this domain is outside that range:

| Intended value | Meaning                          | Fits `numeric(5,2)`?          |
|----------------|----------------------------------|-------------------------------|
| `0.001`        | 1 gram in kilograms              | No — rounds to `0.00`         |
| `0.453592`     | 1 pound in kilograms             | No — rounds to `0.45`         |
| `1000`         | 1 tonne in kilograms             | No — **overflows**, errors    |
| `16`           | 1 ounce in pounds                | Yes                           |

The rounding case is the dangerous one. `COPY` into a `numeric(5,2)` column
**truncates without warning**, so `0.001` is stored as `0.00` and the unit
conversion silently becomes wrong. The overflow case at least raises an error.

## Why it was not caught

`etl/seed_db.sh` loaded `uom` under `session_replication_role = 'replica'`, which
does not affect type conversion, so the truncation was invisible. It was only
found by loading real values through the rewritten loader in `TICKET-020` and
checking what actually landed in the column.

There is no test asserting the precision is sufficient, and no code in the
repository currently performs unit conversion, so nothing consumes the wrong
value yet. The defect is latent, not active.

## Impact

- Any future feature that converts quantities between units will produce wrong
  quantities, with no error, from a value that looks well-formed.
- Loading a `uom` file containing a factor of 1000 or more fails the whole
  table load on overflow.
- `deploy/schema.sql` is a dump of the live database, so the wrong precision is
  also what a fresh environment is built from.

## Proposed fix

- Widen the column to hold realistic conversion factors with margin, for example
  `numeric(20,10)`. This must be done as a migration on the live database, then
  the dump regenerated. The generated SQL is never hand-edited.
- Decide and record the rounding policy for a factor that does not fit exactly
  (round, truncate, or reject), and make the loader enforce it rather than
  inheriting PostgreSQL's silent default.
- Add a schema assertion alongside the existing `tests/test_deploy_assets.py`
  guards, so a regenerated dump cannot silently reintroduce a precision that is
  too small for the domain.

## Notes

- The self-referencing `uom.ref_unit -> uom.unit` relationship is a separate
  issue from this one and is already handled correctly by the loader.
- This defect is invisible to `alembic check` as a *correctness* problem: the
  column type matches the model, so it does not appear among the 94 pending
  operations recorded in `TICKET-019`. It is a modelling error, not model drift.
