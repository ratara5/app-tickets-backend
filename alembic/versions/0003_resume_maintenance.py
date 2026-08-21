"""One maintenance per ticket: reassign children, dedupe, unique constraint.

Implements the migration for OpenSpec change `resume-maintenance-on-start`:

Step A — reassign child records from duplicate maintenances to the survivor
         (earliest `maintenance_id` per `ticket_id`; uuid7 values sort
         chronologically): pauses, photos, worksheets, maintenance
         technicians, maintenance spares.
Step B — delete the remaining duplicate maintenance rows.
Step C — add a unique constraint on `maintenances.ticket_id` so the
         idempotent start flow can rely on flush-time IntegrityError.

Revision ID: 0003_resume_maintenance
Revises: 0002
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_resume_maintenance"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Child tables referencing maintenances.maintenance_id (reassign order).
_CHILD_TABLES = (
    "pauses",
    "photos",
    "worksheets",
    "maintenances_technicians",
    "maintenances_spares",
)

# Rows that have a chronologically-earlier sibling for the same ticket
# (uuid7 compares lexicographically in creation order). These are duplicates.
_DUPLICATES_SQL = """
    SELECT maintenance_id FROM maintenances m
    WHERE EXISTS (
        SELECT 1 FROM maintenances earlier
        WHERE earlier.ticket_id = m.ticket_id
          AND earlier.maintenance_id < m.maintenance_id
    )
"""

# Earliest (survivor) maintenance of the ticket a given child row points to.
_SURVIVOR_OF_CHILD_SQL = """
    SELECT survivor.maintenance_id FROM maintenances survivor
    WHERE survivor.ticket_id = (
        SELECT parent.ticket_id FROM maintenances parent
        WHERE parent.maintenance_id = {child}.maintenance_id
    )
    ORDER BY survivor.maintenance_id ASC
    LIMIT 1
"""


def upgrade() -> None:
    # ── Step A1: drop colliding worksheets before any reassignment ──────────
    # Worksheets are 1:1 (unique maintenance_id). If both the survivor and a
    # duplicate own one, keep the survivor's and delete the orphan first so
    # the move below cannot violate the unique constraint.
    op.execute(
        sa.text(
            f"""
            DELETE FROM worksheets
            WHERE maintenance_id IN ({_DUPLICATES_SQL})
              AND ({_SURVIVOR_OF_CHILD_SQL.format(child="worksheets")}) IN (
                  SELECT w.maintenance_id FROM worksheets w
                  JOIN maintenances s ON s.maintenance_id = w.maintenance_id
                  WHERE NOT EXISTS (
                      SELECT 1 FROM maintenances earlier
                      WHERE earlier.ticket_id = s.ticket_id
                        AND earlier.maintenance_id < s.maintenance_id
                  )
              )
            """
        )
    )

    # ── Step A2: reassign child records to the surviving maintenance ────────
    for table in _CHILD_TABLES:
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET maintenance_id = ({_SURVIVOR_OF_CHILD_SQL.format(child=table)})
                WHERE maintenance_id IN ({_DUPLICATES_SQL})
                """
            )
        )

    # ── Step B: delete duplicate maintenance rows (children already moved) ──
    op.execute(sa.text(f"DELETE FROM maintenances WHERE maintenance_id IN ({_DUPLICATES_SQL})"))

    # ── Step C: enforce one maintenance per ticket at the DB level ──────────
    op.create_unique_constraint(
        "uq_maintenances_ticket_id", "maintenances", ["ticket_id"]
    )


def downgrade() -> None:
    # The constraint is the only schema artifact; reassigned history and
    # deleted duplicates are not restorable.
    op.drop_constraint("uq_maintenances_ticket_id", "maintenances", type_="unique")
