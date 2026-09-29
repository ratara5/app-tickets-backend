# TICKET-021: `uom.factor_conversion` cannot represent real conversion factors

- **Status:** Migration written and proven; awaiting application to live
- **Severity:** High — silent data corruption on every conversion
- **Owner:** ratara5
- **Review by:** 2026-12-27
- **Related:** `TICKET-019`, `TICKET-020`, `TICKET-018`

## Problem

`deploy/schema.sql` declares:

    uom.factor_conversion numeric(5,2)

`numeric(5,2)` keeps two decimal places and holds at most 999.99. Real
unit-conversion factors are published with far more precision than that:

| Intended value | Meaning             | Stored as    | Consequence                     |
|----------------|---------------------|--------------|---------------------------------|
| `0.001`        | 1 gram in kilograms | `0.00`       | factor destroyed                |
| `0.453592`     | 1 pound in kilograms| `0.45`       | silently wrong, looks valid     |
| `0.000000001`  | 1 mg in kg          | `0.00`       | factor destroyed                |
| `1000`         | 1 tonne in kilograms| `1000.00`    | fits, by 0.01                   |

The defect is the **scale**, not the magnitude. `1000` loads fine, so nothing
ever raised an error, and the values that *are* damaged are the small ones that
round to a plausible-looking `0.00` or `0.45`. That is why this is silent.

Live data is not currently damaged: all 9 rows are whole numbers with at most two
decimals (`40.00`, `20.00`, `3.79`, `2.00`, `1.00`) and round-trip unchanged.
The defect is about what the column can represent, not about rows to repair.

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
- A factor needing more than two decimals is destroyed or rounded at load; the
  load itself succeeds, so nothing in the pipeline reports the loss.
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

## Progress

Decided and written:

- **Target type `numeric(20,10)`**, recorded with its reasoning. Ten integer
  digits cover tonne-to-milligram (10**9) and ten decimal places cover the
  published constants, which are exact rationals such as lb -> kg 0.45359237.
  `decimal`, not `float`, because these are exact ratios rather than measurements.
- **Rounding policy: reject.** A factor that does not fit is a data error, and
  rounding it yields a wrong quantity with no signal. The policy is written into
  the revision docstring so it is read before a value is chosen.
- `alembic/versions/0002_widen_uom_factor_conversion.py`, descending from
  `0001_baseline`, 24-character id inside Alembic's `varchar(32)`:
  - `ALTER` rather than drop/recreate, so the data and the self-referencing
    `uom.ref_unit` foreign key survive
  - idempotent: a column already wide enough is left alone, and a partially
    bounded or non-numeric column raises rather than being migrated on a guess
  - reads precision and scale from the inspected *type object*. SQLAlchemy's
    `get_columns` returns them there, not as dict keys; reading the dict keys
    made this revision a silent no-op when it was first written, which is why
    there is a guard test for it
  - `downgrade` narrows back but is documented destructive, and on real data it
    fails with `numeric field overflow` rather than truncating quietly
- Proven on a disposable database built from `deploy/schema.sql`:
  upgrade moves `5,2` -> `20,10`; re-running is a no-op; downgrade round-trips;
  `0.001`, `0.453592`, `0.000000001` and `1000` all store exactly afterwards.
- `tests/test_uom_factor_precision.py`, 14 guards: the migration's chain, id
  length, idempotence, ALTER-not-recreate, and recorded policy, plus five
  assertions that the schema of record is wide enough.

Still open:

- **Apply to live and regenerate the dump.** The dump is derived from live, so
  the five schema assertions are `strict xfail` until the ALTER runs on
  `db_gestiket_acme` and the dump is regenerated. The strict marker means
  hand-editing `deploy/schema.sql` to make them pass is a *failure*, not a
  silent green. Remove the markers in the same commit as the regeneration.
- **Loader-side rejection is not implemented.** The widened column stops the
  corruption by having room for the value, but a factor that genuinely exceeds
  `numeric(20,10)` is still rounded by PostgreSQL rather than refused. This is
  deliberately not done inside this revision: the guard belongs to the loader
  and must cover all five bounded numeric columns
  (`labsdls.hourly_rate`, `maintenances_spares.qty`, `markets.transport_cost`,
  `spares.price`, `uom.factor_conversion`), not just this one. The revision
  docstring says this explicitly rather than implying the policy is enforced.

## Notes

- The self-referencing `uom.ref_unit -> uom.unit` relationship is a separate
  issue from this one and is already handled correctly by the loader.
- This defect is invisible to `alembic check` as a *correctness* problem: the
  column type matches the model, so it does not appear among the 94 pending
  operations recorded in `TICKET-019`. It is a modelling error, not model drift.
- Applying this migration to live also requires repointing `alembic_version`,
  which still holds the deleted `0005_add_upload_replaces_photo_id_fix_parent_tab`
  in a `varchar(64)`. That is `TICKET-015` and its recorded undo procedure.

## Rehearsal 2026-09-29 — is the widening reversible? Measured, not assumed

`0002` has a `downgrade()` that narrows the column back, but it is lossy by
design. Whether that matters was measured on a throwaway database built from
`deploy/schema.sql`, loaded with live's own `uom` rows, before live was touched.

**Round trip with live's 9 rows: reversible, and lossless.** `upgrade` ->
`downgrade` -> `upgrade` leaves every value numerically identical. The only
difference is textual: `numeric(5,2)` renders `40.00` where `numeric(20,10)`
renders `40.0000000000`. The stored numbers are the same, and every row in live
today satisfies `factor_conversion = round(factor_conversion, 2)`, so nothing is
at risk. A snapshot diff shows the scale change and hides the fact that the
values are equal, which is why the comparison was made on the number.

**Round trip with a value that needs precision: irreversible, silently.** Adding
`lb = 0.45359237` and running the same round trip:

```
before downgrade: lb=0.4535923700
AFTER  downgrade: lb=0.45
re-upgraded:      lb=0.4500000000
```

The downgrade does not fail and does not warn. It rounds, and re-upgrading cannot
restore what was discarded. So the honest statement of reversibility is:

- **Before** any precise factor is loaded, the migration can be undone exactly.
- **After** one is loaded, undoing it silently corrupts that value, and the only
  true reversal is restoring a dump taken beforehand.

That boundary is the point of the ticket rather than a flaw in it. A precision
fix that could be silently reverted would reintroduce the original defect without
ever producing an error, which is the property that let this go unnoticed for as
long as the schema has existed.

The rehearsal also surfaced a defect unrelated to precision: live `uom` has two
rows that violate `uom_ref_unit_fkey` while PostgreSQL reports the constraint as
validated, and re-loading `uom` therefore fails. Recorded as TICKET-024.
