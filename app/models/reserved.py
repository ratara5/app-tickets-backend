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

    Excluding the table does not exclude the foreign keys that point at it, and
    those are a second hazard of the same kind. `spares.unit` really does carry a
    foreign key to `uom(unit)` in live, but the model cannot declare it without
    breaking `create_all`, so autogenerate would otherwise report that live
    constraint as surplus and `alembic upgrade head` would drop it. The hook
    therefore filters foreign keys by the table they reference as well.
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


def _foreign_key_target_tables(constraint: Any) -> frozenset[str]:
    """The tables a reflected foreign key points at.

    A `ForeignKeyConstraint` reaches the `include_object` hook as its
    `object`, and each element carries `target_fullname` as a dotted string:
    `"uom.unit"`, or `"public.uom.unit"` when the reference is
    schema-qualified. The table is therefore the second-to-last component, not
    the first, and both forms have to resolve to the same name.
    """
    tables: set[str] = set()
    for element in getattr(constraint, "elements", ()) or ():
        target = getattr(element, "target_fullname", None)
        if not target:
            continue
        parts = target.split(".")
        tables.add(parts[-2] if len(parts) >= 2 else parts[-1])
    return frozenset(tables)


def include_object(
    object: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Alembic `include_object` hook that skips the reserved tables.

    Tables are filtered, and so are foreign keys that point into them. Both
    exclusions exist for the same reason, and the second one is not optional.

    A table in the database with no model is indistinguishable from a table
    nobody wants any more, so it is excluded. But `spares.unit` carries a real
    foreign key to `uom(unit)`, and the model cannot declare it: `Spare` has no
    `ForeignKey("uom.unit")` because `uom` is one of the five reserved tables,
    and an unresolvable reference breaks `Base.metadata.create_all`, which is
    what the test suite builds its schema with. Without this second exclusion
    autogenerate reports the live constraint as a difference and
    `alembic upgrade head` would drop referential integrity that the live
    database deliberately has.

    Only `table` and `foreign_key_constraint` are filtered. A column or an
    index that happens to share a name with a reserved table is still in scope,
    because the reserved names refer to whole tables and not to anything inside
    them. The foreign key is matched on the table it *points at*, never on its
    own name, so an unrelated constraint called `holidays_fkey` stays in scope.
    """
    if type_ == "table" and name in RESERVED_TABLES_WITHOUT_MODELS:
        return False
    if type_ == "foreign_key_constraint":
        if _foreign_key_target_tables(object) & RESERVED_TABLES_WITHOUT_MODELS:
            return False
    return True
