"""change start_hour end_hour to time without timezone

Revision ID: cfec57761e8b
Revises: 7f4d68531ba6
Create Date: 2026-07-09 17:03:35.811828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cfec57761e8b'
down_revision: Union[str, None] = '7f4d68531ba6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "maintenances_technicians",
        "start_hour",
        type_=sa.Time(timezone=False),
        postgresql_using="start_hour::time without time zone"
    )
    op.alter_column(
        "maintenances_technicians",
        "end_hour",
        type_=sa.Time(timezone=False),
        postgresql_using="end_hour::time without time zone"
    )

def downgrade() -> None:
    op.alter_column(
        "maintenances_technicians",
        "start_hour",
        type_=sa.Time(timezone=True),
        postgresql_using="start_hour::timetz"
    )
    op.alter_column(
        "maintenances_technicians",
        "end_hour",
        type_=sa.Time(timezone=True),
        postgresql_using="end_hour::timetz"
    )