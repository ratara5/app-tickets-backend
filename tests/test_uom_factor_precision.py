"""Guards for the uom.factor_conversion widening (TICKET-021).

The defect was a column declared `numeric(5,2)`, which cannot represent a unit
conversion factor: it caps at 9.99 and keeps two decimal places, so `0.001` was
stored as `0.00` and `0.453592` as `0.45`. The silent cases are the dangerous
ones, because the stored value is still a plausible number.

These are static checks plus a review of the migration's own logic. They need no
database: the behavioural proof was run against a disposable instance built from
deploy/schema.sql, and what is asserted here is that the widening, its
idempotence, and the schema of record cannot be undone silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REVISION = ROOT / "alembic" / "versions" / "0002_widen_uom_factor_conversion.py"
SCHEMA_SQL = ROOT / "deploy" / "schema.sql"

REQUIRED_PRECISION = 20
REQUIRED_SCALE = 10

# Values the old type could not hold, and why each one matters. 0.001 and
# 0.453592 were stored WRONGLY; 1000 raised an error, which is how the range
# limit surfaced at all.
REAL_FACTORS = [
    ("0.001", "g -> kg", "silently became 0.00"),
    ("0.453592", "lb -> kg", "silently became 0.45"),
    ("0.000000001", "tonne -> mg", "below the old scale"),
    ("1000", "kg -> tonne", "overflowed the old precision"),
]


@pytest.fixture(scope="module")
def revision() -> str:
    return REVISION.read_text(encoding="utf-8")


# ── The schema of record must actually be wide enough ──────────────────────
def _column_precision_and_scale() -> tuple[int | None, int | None]:
    match = re.search(
        r"^\s+factor_conversion\s+numeric\((\d+),\s*(\d+)\)", SCHEMA_SQL.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, "uom.factor_conversion is missing or unconstrained in the schema of record"
    return int(match.group(1)), int(match.group(2))


def test_schema_of_record_holds_every_real_conversion_factor() -> None:
    """The generated dump is what a new database is built from.

    If it still declares the narrow type, every fresh environment inherits the
    defect regardless of what the migration does, and the migration then has to
    run against every one of them for no reason.
    """
    precision, scale = _column_precision_and_scale()
    assert precision >= REQUIRED_PRECISION, f"precision {precision} is below {REQUIRED_PRECISION}"
    assert scale >= REQUIRED_SCALE, f"scale {scale} is below {REQUIRED_SCALE}"


@pytest.mark.parametrize(
    ("value", "meaning", "why"),
    REAL_FACTORS,
)
def test_every_real_factor_fits_the_declared_column(value: str, meaning: str, why: str) -> None:
    """The point of the widening, asserted against the actual DDL.

    `Decimal.quantize` does not truncate, it raises, so this is an exact check
    rather than a comparison: a factor that cannot be represented exactly here
    would be altered on the way in.
    """
    from decimal import Decimal

    precision, scale = _column_precision_and_scale()
    quantised = Decimal(value).quantize(Decimal(1).scaleb(-scale))
    assert quantised == Decimal(value), f"{value} ({meaning}, {why}) does not survive scale {scale}"

    max_value = Decimal(10) ** (precision - scale)
    assert abs(Decimal(value)) < max_value, f"{value} ({meaning}) exceeds precision {precision}"


# ── The migration itself ───────────────────────────────────────────────────


def test_migration_descends_from_the_baseline(revision: str) -> None:
    """It has to be in the history, or it will never be applied.

    A new revision whose down_revision is not the current head becomes a second
    head, which is the exact condition the baseline squash removed.
    """
    assert re.search(r'^revision: str = "0002_widen_uom_factor"', revision, re.MULTILINE)
    assert re.search(r'^down_revision: str \| None = "0001_baseline"', revision, re.MULTILINE)


def test_migration_id_fits_the_version_column(revision: str) -> None:
    """`alembic_version.version_num` is varchar(32) by Alembic's own DDL.

    The deleted history failed precisely here, with 35- and 48-character ids.
    """
    match = re.search(r'^revision: str = "([^"]+)"', revision, re.MULTILINE)
    assert match
    assert len(match.group(1)) <= 32, f"revision id is {len(match.group(1))} characters"


def test_migration_is_idempotent(revision: str) -> None:
    """Re-running against an already-widened column must be a no-op.

    A database built from the regenerated dump starts out at the target type, and
    a migration that unconditionally re-alters will rewrite the table on every
    deploy. The guard also has to read precision and scale correctly: SQLAlchemy's
    get_columns returns them on the type object, not as dict keys, and reading
    the wrong place made this migration a silent no-op when it was first written.
    """
    assert "_is_already_wide_enough" in revision
    assert "if _is_already_wide_enough" in revision
    # The guard is fed from the type object, not from get_columns() dict keys.
    assert re.search(r'column_type\s*=\s*columns\[COLUMN\]\["type"\]', revision)
    assert "column_type.precision" in revision and "column_type.scale" in revision


def test_migration_refuses_an_unexpected_column_type(revision: str) -> None:
    """If `uom` or the column has changed shape, stop rather than guess."""
    assert "not a numeric type" in revision
    assert "does not exist" in revision


def test_migration_widens_rather_than_recreates(revision: str) -> None:
    """ALTER, not DROP/CREATE, so the data and the self-reference survive.

    uom has a self-referencing foreign key. Recreating the table would drop
    uom_ref_unit_fkey and every row with it.
    """
    assert "op.alter_column" in revision
    assert "op.drop_table" not in revision
    assert "op.create_table" not in revision


def test_downgrade_documents_that_it_is_destructive(revision: str) -> None:
    """The narrowing path must not look safe.

    It is real and it is lossy, and it will fail on real data rather than
    truncating quietly, which is the acceptable outcome. The docstring has to say
    so, because "downgrade exists" reads as "reversible" otherwise.
    """
    body = revision.split("def downgrade", 1)[1]
    docstring = body.split('"""', 2)[1].lower()
    assert "destructive" in docstring
    assert "truncat" in docstring or "lose" in docstring
    # It must be a real ALTER and not a silent no-op round trip.
    assert "op.alter_column" in body


# ── The rounding policy is stated, not left to the database ───────────────


def test_records_the_rounding_policy_as_reject(revision: str) -> None:
    """A factor that does not fit is refused, not rounded.

    Rounding a conversion factor produces a wrong quantity with no signal, so the
    policy has to be written down where someone will read it before choosing a
    value.
    """
    assert "reject" in revision.lower()
    docstring = revision.split('"""', 2)[1].lower()
    assert "round" in docstring
    assert "wrong" in docstring or "signal" in docstring


def test_justifies_the_chosen_width(revision: str) -> None:
    """The numbers are arguable, so the reasoning must be recorded.

    A bare `numeric(20,10)` invites the next person to 'fix' it to something
    smaller without knowing why.
    """
    docstring = revision.split('"""', 2)[1]
    assert "Why 20,10" in docstring
    for reason in ("Precision", "Magnitude", "exact rational"):
        assert reason in docstring, f"the width justification is missing {reason}"


def test_documents_that_this_is_not_model_drift(revision: str) -> None:
    """`uom` has no model, so `alembic check` will never report this.

    Without that note, the next person will look for the 94 pending operations
    and conclude the type is fine because it is not in the list.
    """
    docstring = revision.split('"""', 2)[1].lower()
    assert "not model drift" in docstring or "modelling error" in docstring
    assert "excluded from" in docstring
