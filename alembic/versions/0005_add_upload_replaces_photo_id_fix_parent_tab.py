"""Add uploads_sessions.replaces_photo_id and fix parent_tab type.

The UploadSession ORM (photo-replace-delete) expects a `replaces_photo_id`
column and stores `parent_tab` (e.g. "maintenances") as a string, but the live
`uploads_sessions` table was created with `parent_tab UUID` and no
`replaces_photo_id`. Every `POST /uploads/init` therefore 500s before any chunk
is uploaded. This migration aligns the table with the ORM.

Revision ID: 0005_add_upload_replaces_photo_id_fix_parent_tab
Revises: 0003_resume_maintenance
Create Date: 2026-09-03

NOTE: `down_revision` is pinned to `0003_resume_maintenance` (the current live
`alembic_version`). Migration `0004_align_photos_maintenance_id_fk` was already
reflected in the database out-of-band (photos.maintenance_id is uuid with the
canonical FK name), so this migration does not depend on it to avoid re-applying
already-present DDL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_add_upload_replaces_photo_id_fix_parent_tab"
down_revision: Union[str, None] = "0003_resume_maintenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Align parent_tab with the String column in the ORM model. Existing rows
    # hold UUID values, so cast them to their text representation.
    op.alter_column(
        "uploads_sessions",
        "parent_tab",
        type_=sa.Text(),
        postgresql_using="parent_tab::text",
    )

    # Add the replaces_photo_id column the ORM expects (nullable, no FK since it
    # may reference photos rows that the replace logic deletes).
    op.add_column(
        "uploads_sessions",
        sa.Column("replaces_photo_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("uploads_sessions", "replaces_photo_id")
    op.alter_column(
        "uploads_sessions",
        "parent_tab",
        type_=sa.Uuid(),
        postgresql_using="parent_tab::uuid",
    )