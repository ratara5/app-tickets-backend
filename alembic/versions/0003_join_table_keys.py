"""give the join tables primary keys, and settle the maintenance/ticket uniqueness

The models already declare composite primary keys on `maintenances_spares` and
`maintenances_technicians` (`app/models/maintenance.py`), and the live tables have
none at all. This revision brings the live tables up to the models. It is the
second half of TICKET-019: the first half reconciled ~50 model definitions, and
this closes the remaining differences in the database itself.

Autogenerate cannot see this
----------------------------
A missing primary key is invisible to `alembic check`, which reported nine
items, none of them these two. Autogenerate detects added and removed
*constraints by name* and never compares primary keys, so two join tables with no
primary key looked identical to two join tables with one. This was found by
querying `pg_constraint` directly, and it is worth knowing that the gap is silent
by construction rather than by accident.

It matters more than a missing constraint usually would
-------------------------------------------------------
On 2026-09-29 a restore drill replayed a full-instance dump onto the running
server. `CREATE DATABASE` failed as "already exists", the script connected to the
existing database anyway, and 20 of 23 tables rejected the duplicated rows on
their primary keys. `maintenances_spares` and `maintenances_technicians` did not,
because they had no key to reject them, so both silently doubled — 3 rows to 6,
5 to 10 — in the operational record of a system under test. It was caught only by
diffing row counts against a baseline. A primary key on a join table is what turns
a failed restore into a loud one.

Semantics of the key on `maintenances_technicians`
--------------------------------------------------
The key is `(maintenance_id, technician_id)`, as the model declares it, which
means a technician may be assigned to a given maintenance only once and
`start_hour`/`end_hour` are not part of the identity. That forecloses a split
shift, where one technician works two separated periods within the same
maintenance. Live data does not exercise the case: all 5 rows are distinct on
`(maintenance_id, technician_id)`, so this revision is a no-op against it. If a
split shift turns out to be a real requirement, the key should become
`(maintenance_id, technician_id, start_hour)` in both the model and here. That is
a modelling decision rather than a drift fix, so it is flagged rather than taken
unilaterally.

The duplicate unique constraint
-------------------------------
`maintenances` carries two unique constraints over the same single column:

    maintenances_ticket_id_key    UNIQUE (ticket_id)
    uq_maintenances_ticket_id     UNIQUE (ticket_id)

PostgreSQL auto-generated the first at table creation and the second was added
explicitly to match the model. They enforce exactly the same rule, so the
unnamed one is redundant, and the model declares only `uq_maintenances_ticket_id`.
Dropping the auto-generated one is therefore a pure de-duplication: no uniqueness
guarantee is lost, because the surviving constraint is identical.

Data safety
-----------
Every statement is checked before it runs. The primary keys are only added after
confirming that no existing row duplicates the key and that no key column holds
NULL, so the revision cannot fail halfway and leave a half-constrained table. All
current live data satisfies both: 3 distinct `(maintenance_id, spare_id)` of 3
rows, 5 distinct `(maintenance_id, technician_id)` of 5 rows, and no NULLs in any
column being made NOT NULL.

The NOT NULL changes are stated explicitly even though adding a primary key
already implies them. Relying on that side effect would tie a durability property
to the continued existence of a different constraint.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

#: 18 characters, comfortably inside alembic_version.version_num varchar(32).
revision: str = "0003_join_table_keys"
down_revision: str | None = "0002_widen_uom_factor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The composite key each join table's model declares.
JOIN_TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "maintenances_spares": ("maintenance_id", "spare_id"),
    "maintenances_technicians": ("maintenance_id", "technician_id"),
}

#: Columns to make NOT NULL: the three key/scalar columns of each join table,
#: plus the maintenance reference on `pauses`, which has no key to imply it.
NOT_NULL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("maintenances_spares", "maintenance_id"),
    ("maintenances_spares", "spare_id"),
    ("maintenances_spares", "qty"),
    ("maintenances_technicians", "maintenance_id"),
    ("maintenances_technicians", "technician_id"),
    ("maintenances_technicians", "start_hour"),
    ("maintenances_technicians", "end_hour"),
    ("pauses", "maintenance_id"),
)

#: The redundant auto-generated constraint on `maintenances.ticket_id`. The
#: model-declared `uq_maintenances_ticket_id` enforces the same rule and stays.
REDUNDANT_UNIQUE = "maintenances_ticket_id_key"
KEPT_UNIQUE = "uq_maintenances_ticket_id"


def _existing_primary_key(table: str) -> tuple[str, ...] | None:
    """Return the table's primary key columns, or None when it has no primary key."""
    columns = tuple(
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                WHERE c.conrelid = to_regclass(:table) AND c.contype = 'p'
                ORDER BY array_position(c.conkey, a.attnum)
                """
            ),
            {"table": table},
        )
        .scalars()
    )
    # A table with no primary key yields no rows, and tuple() over an empty
    # result is (), which is a real tuple and therefore not None. Returning it
    # unchanged makes a missing key indistinguishable from a malformed one.
    return columns or None


def _assert_key_is_addable(table: str, columns: tuple[str, ...]) -> None:
    """Refuse to add a primary key the existing rows cannot satisfy.

    PostgreSQL would reject the statement with a duplicate-key error naming a
    constraint this revision has not created yet, which is a poor explanation of
    what actually went wrong. Saying which table and which key collide is the
    difference between a diagnosable failure and a puzzling one.
    """
    bind = op.get_bind()
    key_list = ", ".join(f'"{column}"' for column in columns)
    any_null = " OR ".join(f'"{column}" IS NULL' for column in columns)

    null_rows = bind.execute(
        sa.text(f"SELECT count(*) FROM {table} WHERE {any_null}")  # noqa: S608
    ).scalar_one()
    if null_rows:
        raise RuntimeError(
            f"{table} has {null_rows} row(s) with a NULL in {key_list}, which a "
            "primary key over those columns cannot accept. Resolve the NULLs "
            "before running this revision."
        )

    duplicates = bind.execute(
        sa.text(
            f"SELECT {key_list}, count(*) FROM {table} GROUP BY {key_list} "  # noqa: S608
            "HAVING count(*) > 1"
        )
    ).all()
    if duplicates:
        listed = "; ".join(
            f"({', '.join(str(part) for part in row[:-1])}) x{row[-1]}"
            for row in duplicates
        )
        raise RuntimeError(
            f"{table} has duplicate rows on the key {key_list}, so the primary "
            f"key the models declare cannot be added: {listed}. Decide which row "
            "survives before running this revision."
        )


def upgrade() -> None:
    """Bring the live join tables and maintenances up to the model declarations."""
    inspector = sa.inspect(op.get_bind())

    if REDUNDANT_UNIQUE in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("maintenances")
    }:
        op.drop_constraint(
            REDUNDANT_UNIQUE, "maintenances", type_="unique"
        )
        kept = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("maintenances")
        }
        if KEPT_UNIQUE not in kept:
            raise RuntimeError(
                f"Dropped {REDUNDANT_UNIQUE} but {KEPT_UNIQUE} is absent, so "
                "maintenances.ticket_id would be left without any uniqueness "
                "guarantee. Refusing to continue."
            )

    for table, columns in JOIN_TABLE_KEYS.items():
        existing = _existing_primary_key(table)
        if existing is not None:
            if existing != columns:
                raise RuntimeError(
                    f"{table} has a primary key on {existing}, but the models "
                    f"declare {columns}. Reconcile the model before running this "
                    "revision."
                )
            continue
        _assert_key_is_addable(table, columns)
        op.create_primary_key(f"{table}_pkey", table, columns)

    for table, column in NOT_NULL_COLUMNS:
        op.alter_column(table, column, nullable=False)


def downgrade() -> None:
    """Remove the keys and relax the columns.

    The primary keys go first, because PostgreSQL refuses to drop NOT NULL from a
    column that is still part of a primary key. Reversing the two would fail with
    `column "..." is in a primary key`.

    Dropping a primary key does not relax the columns it covered, so the NOT NULL
    changes are reversed explicitly. This returns the tables to the state TICKET-019
    recorded as the defect; it is not a recovery path, because the tables it
    recreates are the ones that let a failed restore corrupt data silently.
    """
    for table in JOIN_TABLE_KEYS:
        if _existing_primary_key(table) is not None:
            op.drop_constraint(f"{table}_pkey", table, type_="primary")

    for table, column in reversed(NOT_NULL_COLUMNS):
        op.alter_column(table, column, nullable=True)

    op.create_unique_constraint(REDUNDANT_UNIQUE, "maintenances", ["ticket_id"])
