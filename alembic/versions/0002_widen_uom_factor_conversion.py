"""widen uom.factor_conversion, which cannot represent a conversion factor

`uom.factor_conversion` is `numeric(5,2)`: two decimal places, and at most 999.99.
Real conversion factors need far more precision than that, and when one is
loaded PostgreSQL rounds it to fit without warning:

| intended     | meaning        | `numeric(5,2)` result       |
|--------------|----------------|-----------------------------|
| `0.001`      | g -> kg        | `0.00` — silently zeroed    |
| `0.453592`   | lb -> kg       | `0.45` — silently wrong     |
| `1000`       | kg -> tonne    | `1000.00`, fits by 1 dp     |

So the defect is the scale, not the magnitude: only 9 of the values that matter
are affected by rounding, and a value such as `1000` still loads, which is why
nothing ever failed. The stored value always looks well-formed, and it is
wrong. That is the property that let this go unnoticed for as long as the
schema has existed.

Live data is not currently damaged. All 9 rows are whole numbers with at most
two decimals, so they survive the round trip unchanged. This migration is about
what the column can represent going forward, not about repairing rows.

This revision widens the column to `numeric(20,10)`. Widening is a rewrite but
not a lossy one: existing values are preserved exactly.

Why 20,10
----------
Two failure directions have to be covered, and the column has to serve both.

*Precision.* Conversion factors between real units need up to 10 significant
decimal places, because they are exact rationals and the published constants are
long: lb -> kg is 0.45359237, kg -> lb is 2.20462262, mile -> km is 1.609344.
Two decimal places is short by four orders of magnitude.

*Magnitude.* The factor is the ratio of one unit to another, so it can be far
below 1 (mg -> kg is 0.000000001) or far above it (kg -> tonne is 1000, and
tonne -> tonne-gram is 10**9). `numeric(5,2)` holds 999.99, so the large end is
nearly adequate; the small end is not, and neither end has the decimal places
that these constants are published with.

`numeric(20,10)` holds 10 integer digits and 10 decimal places: 9_999_999_999.
9999999999 down to 0.0000000001. That is the whole plausible range for linear
unit conversion, and decimal is the right type here because these factors are
exact rationals rather than measurements — a float64 would introduce error the
column does not need.

Rounding policy: reject, never round
------------------------------------
A conversion factor that does not fit is a data error, and rounding it produces
a wrong quantity with no signal. So the policy is that a factor which cannot be
represented exactly is refused at load time, not silently adjusted.

That policy is implemented. `etl/seed_db.sh` stages the CSV as text and refuses
any value a bounded numeric cannot hold exactly, naming the column, the value and
the type it was being stored as. It reads precision and scale from the schema of
record rather than naming tables, so it covers all five bounded numeric columns
and a column added by a later migration is covered without touching the loader.
This revision is what gives the policy room to work: before it, a factor needing
more than two decimal places was rounded by the database with no error, which is
how the wrong values got in. See `tests/test_seed_loader.py`.

This is a modelling error, not model drift
------------------------------------------
`uom` is one of the five tables kept for unbuilt features and is excluded from
Alembic's metadata (TICKET-018), so `alembic check` does not report this. The
column type is not wrong relative to a model; there is no model. It was found by
loading real values through the rewritten loader (TICKET-020) and checking what
actually landed in the column.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

#: 24 characters, comfortably inside alembic_version.version_num varchar(32).
revision: str = "0002_widen_uom_factor"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "uom"
COLUMN = "factor_conversion"
OLD_TYPE = sa.Numeric(precision=5, scale=2)
NEW_TYPE = sa.Numeric(precision=20, scale=10)


def _current_precision_and_scale() -> tuple[int | None, int | None]:
    """Read the column's declared precision and scale.

    SQLAlchemy's `get_columns` does not populate separate `precision` and `scale`
    keys for a `NUMERIC`; both come back as None and the real values live on the
    type object as `NUMERIC(precision=5, scale=2)`. Reading the dict keys instead
    of the type made this revision a no-op, silently, which is the failure mode
    this guard exists to prevent.
    """
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    if COLUMN not in columns:
        raise RuntimeError(
            f"{TABLE}.{COLUMN} does not exist. A database without the reserved "
            "reference tables predates TICKET-018 and is not a supported target "
            "for this revision."
        )

    column_type = columns[COLUMN]["type"]
    if not isinstance(column_type, sa.Numeric):
        raise RuntimeError(
            f"{TABLE}.{COLUMN} is {column_type!r}, not a numeric type. This "
            "revision exists to widen a numeric, and something has replaced it."
        )
    return column_type.precision, column_type.scale


def _is_already_wide_enough(precision: int | None, scale: int | None) -> bool:
    """True when the column can already represent every value we intend to store.

    An unconstrained numeric (precision and scale both NULL) has no bound and is
    therefore always sufficient.
    """
    if precision is None and scale is None:
        return True
    if precision is None or scale is None:
        # A partially bounded numeric is not a shape PostgreSQL produces, and it
        # is not something this revision should reason about. Refuse rather than
        # guess.
        raise RuntimeError(
            f"{TABLE}.{COLUMN} has a partially bounded numeric type "
            f"(precision={precision}, scale={scale}); refusing to migrate it."
        )
    return precision >= NEW_TYPE.precision and scale >= NEW_TYPE.scale


def upgrade() -> None:
    """Widen the column so conversion factors can be stored exactly."""
    precision, scale = _current_precision_and_scale()
    if _is_already_wide_enough(precision, scale):
        return
    op.alter_column(
        TABLE,
        COLUMN,
        type_=NEW_TYPE,
        existing_type=OLD_TYPE,
        existing_nullable=True,
    )


def downgrade() -> None:
    """Narrow the column back, losing precision.

    This is destructive and is provided for completeness rather than as a
    recovery path: narrowing truncates every value that needs more than two
    decimal places, and would overflow for a factor above 9.99. Expect it to fail
    on real data rather than to succeed quietly.
    """
    precision, scale = _current_precision_and_scale()
    if (precision, scale) == (OLD_TYPE.precision, OLD_TYPE.scale):
        return
    op.alter_column(
        TABLE,
        COLUMN,
        type_=OLD_TYPE,
        existing_type=NEW_TYPE,
        existing_nullable=True,
    )
