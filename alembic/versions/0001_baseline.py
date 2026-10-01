"""baseline: adopt the live schema, replacing a history that was never applied

This revision creates nothing. It is an anchor, not a schema.

Why it exists
-------------
The database this project runs was built by hand and by the ETL loader. Alembic
never migrated it. Its `alembic_version` table was stamped by hand and held one
row: a 48-character revision id, in a `varchar(64)` column that Alembic's own DDL
creates as `varchar(32)`. The seven revisions that purported to describe how the
schema got here were a record of a path nobody walked, and they could not be run:
two heads, and ids too long to store in the table meant to store them.

So the history is not repaired and not replayed. It is replaced. The live schema
is the ground truth, it is captured in `infra/schema.sql`, and this revision
declares that state as the starting point.

How the schema is actually built
--------------------------------
New and disposable databases are built from the dump, not from this migration:

    psql -v ON_ERROR_STOP=1 -d <db> < infra/schema.sql

Then bring the database under Alembic's bookkeeping:

    alembic stamp head

`infra/schema.sql` is a `pg_dump --schema-only` of the live database and is
verified to build a working schema on a stock PostgreSQL 16 with only the
pg_uuidv7 extension added. It is the schema of record, and this revision exists
only so that later migrations have something to be a descendant of.

A baseline that also re-created every table was considered and rejected. It would
duplicate 1140 lines of DDL, and the copy would be a second artifact free to
drift from the dump - which is exactly the failure that produced
`tests/test_init_sql_schema.py`'s predecessor and the deleted `init.sql`.

Going forward
-------------
New revisions descend from this one, and `alembic check` becomes meaningful: it
compares the models against a database and fails when they have diverged. That
comparison is only trustworthy because env.py now imports every model and
excludes the five tables kept for unbuilt features (TICKET-018, TICKET-019).

The models are still known to be stale in several places. Those are ordinary
migrations from here, not repairs to this baseline.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

#: 14 characters, comfortably inside alembic_version.version_num varchar(32).
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema change: this revision declares the adopted starting point.

    The database already carries this state. See the module docstring for how a
    new database is built and stamped.
    """


def downgrade() -> None:
    """No schema change, so there is nothing to reverse."""
