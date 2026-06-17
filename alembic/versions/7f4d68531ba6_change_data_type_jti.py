"""change data type jti

Revision ID: 7f4d68531ba6
Revises: 0001
Create Date: 2026-06-17 17:53:06.875685

"""
from typing import Sequence, Union
from sqlalchemy import Uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f4d68531ba6'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'token_blacklist',
        'jti',
        existing_type=sa.String(36),
        type_=Uuid(),
        postgresql_using="jti::uuid"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'token_blacklist',
        'jti',
        existing_type=Uuid(),
        type_=sa.String(36)
    )
