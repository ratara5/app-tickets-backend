"""Tables that exist in the database and deliberately have no model.

Five tables were created in the live database by hand and never modelled,
because the features that need them are unbuilt. They are kept for those future
features, and their decision, owner and review date live in TICKET-018.

They create a specific hazard for Alembic. Autogenerate compares
`target_metadata` against the database it is connected to and emits the
difference, and a table that is present in the database but absent from the
models is indistinguishable from a table nobody wants any more. So without an
explicit exclusion, `alembic revision --autogenerate` proposes `drop_table` for
all five, and applying that revision deletes them.

The exclusion is therefore declared here, once, in a name a reviewer can read,
rather than being implied by the absence of a model. `tests/test_alembic_env.py`
checks that this list is exactly the set of tables in `deploy/schema.sql` that no
model describes, so a sixth unmodelled table fails the test rather than reaching
production as a pending `drop_table`.
"""
from __future__ import annotations

from typing import Any

RESERVED_TABLES_WITHOUT_MODELS: frozenset[str] = frozenset(
    {
        # Spelled with a double L because that is how the table exists in the live
        # database. Renaming it is a separate, explicitly-approved change recorded
        # in TICKET-018; correcting the spelling here would silently point the
        # exclusion at a table that does not exist and re-expose the real one to
        # `drop_table`.
        "hollidays",
        "materials",
        "preliquidated",
        "services",
        "uom",
    }
)


def include_object(
    object: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Alembic `include_object` hook that skips the reserved tables.

    Only `type_ == "table"` is filtered. A column or an index that happens to
    share a name with a reserved table is still in scope, because the reserved
    names refer to whole tables and not to anything inside them.
    """
    if type_ == "table" and name in RESERVED_TABLES_WITHOUT_MODELS:
        return False
    return True
