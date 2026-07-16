"""add pause autoincremental

Revision ID: 0002
Revises: cfec57761e8b
Create Date: 2026-07-16 09:30:01.07005

"""
from typing import Sequence, Union
from sqlalchemy import Uuid

from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = 'cfec57761e8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        CREATE SEQUENCE IF NOT EXISTS pauses_pause_id_seq;
        ALTER TABLE pauses 
            ALTER COLUMN pause_id TYPE INTEGER USING pause_id::integer;
        ALTER TABLE pauses 
            ALTER COLUMN pause_id SET DEFAULT nextval('pauses_pause_id_seq');
        SELECT setval('pauses_pause_id_seq', COALESCE(MAX(pause_id), 0) + 1) 
            FROM pauses;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE pauses ALTER COLUMN pause_id DROP DEFAULT;
        DROP SEQUENCE IF EXISTS pauses_pause_id_seq;
    """)
