"""Guards for the reference/demo data loader.

These are static checks. They do not need a database, so they run in CI. The
behavioural proof (a self-referencing table loads in any row order, a dangling
reference is rejected, the schema of record is left untouched) was established
against a disposable database built from deploy/schema.sql; what is asserted
here is that the properties which made that proof possible cannot be removed
without a test failing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SEED_SCRIPT = Path(__file__).resolve().parents[1] / "etl" / "seed_db.sh"
SCHEMA_SQL = Path(__file__).resolve().parents[1] / "deploy" / "schema.sql"

# Only line-leading comments are stripped. Inline '#' cannot be removed safely:
# the script uses ${#array[@]} and ${var#prefix} inside quoted strings.
LINE_COMMENT = re.compile(r"^\s*#.*$", re.MULTILINE)


@pytest.fixture(scope="module")
def script() -> str:
    return SEED_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code_only(script: str) -> str:
    """The script with comments removed.

    The comments deliberately document the bypass that was removed and why, so a
    naive substring check would pass on prose while the code regressed. Only
    line-leading comments are stripped, because '#' also appears inside the
    script's quoted strings as ${#array[@]} and ${var#prefix}.
    """
    return LINE_COMMENT.sub("", script)


# ── The defect this script was rewritten for (TICKET-020) ──────────────────


def test_never_disables_triggers_or_fk_enforcement(code_only: str) -> None:
    """session_replication_role='replica' is what allowed an orphaned FK row.

    It switched off referential integrity for every table the loop touched, and
    the orphaned spares.unit -> uom.unit row in the live database is what it
    produced. It must never come back, in any spelling.
    """
    assert "session_replication_role" not in code_only
    # The other spellings of the same bypass.
    assert "replication_role" not in code_only
    # session-level FK disabling, for completeness
    for banned in ("foreign_keys", "SET CONSTRAINTS ALL DEFERRED", "session_replication_role"):
        assert banned not in code_only, f"{banned} reappeared in the loader"


def test_does_not_alter_the_schema_of_record(code_only: str) -> None:
    """A data script must not change the schema.

    The DEFERRABLE approach was abandoned precisely because PostgreSQL would not
    let the constraint be restored while deferred trigger events were pending,
    leaving uom_ref_unit_fkey permanently deferrable. The staging approach must
    therefore never issue DDL.
    """
    ddl = [
        token
        for token in ("ADD CONSTRAINT", "DROP CONSTRAINT", "ALTER COLUMN", "DEFERRABLE", "CREATE INDEX")
        if token in code_only
    ]
    assert ddl == [], f"the loader now issues DDL: {ddl}"


def test_runs_with_stop_on_error(code_only: str) -> None:
    """A failed statement must abort rather than be reported as a success."""
    assert "ON_ERROR_STOP=1" in code_only


# ── Self-referencing table handling ────────────────────────────────────────


def test_self_referencing_table_is_staged_not_bypassed(script: str) -> None:
    """uom.ref_unit -> uom.unit is a genuine cycle, so ordering alone fails.

    It is handled by staging into a TEMP table and inserting parent-before-child.
    The entry must stay in SELF_REF_LOADS and name the real self-reference
    column, or a derived unit loaded above its base unit will fail.
    """
    assert "SELF_REF_LOADS=" in script
    match = re.search(r'SELF_REF_LOADS=\("([^"]+)"\)', script)
    assert match, "SELF_REF_LOADS is empty, but uom.ref_unit -> uom.unit exists"
    entry = match.group(1)
    table, ref_column, columns = entry.split(":")
    assert table == "uom"
    assert ref_column == "ref_unit"
    # The staged column list must match the table, or the INSERT selects wrongly.
    assert columns == "unit,magnitude,uom_description,ref_unit,factor_conversion"


def test_self_reference_constraint_is_immediate_in_the_schema_of_record() -> None:
    """The staging approach is only necessary while the constraint is immediate.

    If someone ever makes this DEFERRABLE in the schema of record, this test
    should fail so the loader can be simplified rather than left needlessly
    complex. It also documents why the loader does not touch constraints.
    """
    assert "uom_ref_unit_fkey" in SCHEMA_SQL.read_text(encoding="utf-8")
    assert not re.search(
        r"uom_ref_unit_fkey[^;]*DEFERRABLE",
        SCHEMA_SQL.read_text(encoding="utf-8"),
        re.IGNORECASE,
    )


# ── Load allowlist: a CSV name becomes a table name ───────────────────────


def test_declares_an_explicit_allowlist(script: str) -> None:
    """Without an allowlist, dropping tickets.csv COPYs straight into tickets.

    The table name is derived from the filename, so the allowlist is the
    security boundary for this script, not a convenience.
    """
    assert "REFERENCE_TABLES=(" in script
    assert "BUSINESS_TABLES=(" in script


def test_reference_data_is_the_allowlisted_default(script: str) -> None:
    """Reference data must be loadable without any extra flag.

    uom and hollidays are the only seeded tables with no dependency on business
    rows, so they are the only ones that may be loaded near production.
    """
    reference = re.search(r"REFERENCE_TABLES=\(([^)]*)\)", script)
    assert reference
    names = reference.group(1).split()
    assert "uom" in names
    assert "hollidays" in names, "the live table is spelled with a double L"


def test_no_reference_to_the_non_existent_single_l_table(script: str) -> None:
    """`holidays` does not exist. Live spells it `hollidays`, with two Ls.

    The loader previously used the single-L name in its allowlist, so the
    reference-data load would have failed on a table name that has never existed.
    Asserting the correct name is not enough, because a future edit can add the
    wrong one back alongside it.
    """
    for match in re.finditer(r"\bholidays\b", script):
        line = script[: match.start()].splitlines()[-1]
        assert "hollidays" not in line, f"single-L 'holidays' on a line that also names the real table: {line!r}"
    assert not re.search(r"\bholidays\b", script), "the loader references a table that does not exist"


def test_every_connection_names_its_database_explicitly(script: str) -> None:
    """A psql call with no -d silently falls back to a database named after the role.

    That works only for a role that happens to own a same-named database, which is
    how the existence check passed while running as `postgres`. Under the
    least-privilege runtime role — which owns nothing by design — it fails
    outright, so the check was incompatible with the role model it was supposed
    to support.

    The guarantee lives in the wrapper, so the wrapper is what is asserted: a
    call site that invokes `psql_db` inherits the `-d` from its definition.
    """
    wrapper = re.search(r"^psql_db\(\)\s*\{.*$", script, re.MULTILINE)
    assert wrapper, "no psql_db wrapper"
    assert '-d "$DB_NAME"' in wrapper.group(0), "the wrapper does not pin the database"

    # Any psql invoked directly, bypassing the wrapper, must name it too.
    for line in script.splitlines():
        stripped = line.strip()
        if "psql" not in stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("psql_db()"):
            continue  # the wrapper itself, asserted above
        assert "psql_db" in stripped or '-d "$DB_NAME"' in stripped, (
            f"psql invoked outside the wrapper without naming a database: {stripped!r}"
        )


def test_the_loader_never_lists_pg_database_to_check_existence(script: str) -> None:
    """Asking the target database whether it is itself is the portable check.

    Listing the catalog requires a connection to some *other* database, which is
    the connection the least-privilege role is least likely to be able to make.
    Comments are stripped, because the file explains at length why this query is
    no longer used.
    """
    executable = re.sub(r"^\s*#.*$", "", script, flags=re.MULTILINE)
    assert "pg_database" not in executable


@pytest.mark.parametrize(
    "table",
    ["materials", "services", "preliquidated"],
)
def test_business_tables_are_classified_as_business_not_reference(script: str, table: str) -> None:
    """These look like reference data but are line items on a live record.

    materials.maintenance_id and services.maintenance_id reference maintenances;
    preliquidated.ticket_id is NOT NULL and references tickets. Loading them
    requires business rows to already exist, so they are never reference data
    and must stay behind --allow-business-data.
    """
    reference = re.search(r"REFERENCE_TABLES=\(([^)]*)\)", script)
    business = re.search(r"BUSINESS_TABLES=\(([^)]*)\)", script)
    assert table not in reference.group(1).split(), f"{table} was misfiled as reference data"
    assert table in business.group(1).split(), f"{table} is missing from the business allowlist"


def test_business_data_requires_an_explicit_opt_in(script: str) -> None:
    assert "--allow-business-data" in script
    assert "ALLOW_BUSINESS_DATA" in script


def test_offers_a_dry_run(script: str) -> None:
    assert "--dry-run" in script
    assert "DRY_RUN" in script


# ── Post-condition: prove the load, do not assume it ───────────────────────


def test_verifies_orphans_after_loading(code_only: str) -> None:
    """Nothing verified the result when triggers were disabled.

    The replacement has to actively prove referential integrity, by building one
    left-join count per outgoing foreign key of every loaded table.
    """
    assert "pg_constraint" in code_only
    assert "LEFT JOIN" in code_only
    assert "orphaned row" in code_only


def test_cleans_up_its_temporary_files(script: str) -> None:
    assert "rm -rf" in script
    assert "CONTAINER_DATA_DIR" in script
