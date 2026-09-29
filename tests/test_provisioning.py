"""Guards for the database provisioning script.

The script is a Plane 1 (admin, one-time) artifact, run by hand. It cannot be
tested at runtime in CI because there is no database, and because running it
would create roles on a shared instance. What is asserted here is that the
privilege boundaries it claims to establish cannot be quietly removed: the grants
and the revokes are the whole point of the file, and a well-meaning edit that
drops one of them fails a test rather than shipping.

The behavioural matrix was established against a disposable PostgreSQL instance:
the runtime role could SELECT, INSERT and use sequences; CREATE TABLE, DROP
TABLE and ALTER TABLE were all denied; the migration role could do DDL; and the
runtime role could not connect to a second database on the same server.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROVISION_DIR = Path(__file__).resolve().parents[1] / "deploy" / "provision"
PROVISION_SQL = PROVISION_DIR / "001-create-application-roles.sql"
PROVISION_README = PROVISION_DIR / "README.md"

# Comments are stripped for the grant assertions: the file documents the
# privileges it withholds as prominently as the ones it grants, so a substring
# check over the raw text would pass on prose alone.
LINE_COMMENT = re.compile(r"^\s*--.*$", re.MULTILINE)


@pytest.fixture(scope="module")
def script() -> str:
    return PROVISION_SQL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(script: str) -> str:
    """Executable SQL only: comments and psql meta-commands removed."""
    return LINE_COMMENT.sub("", script)


# ── Placeholders must not survive ──────────────────────────────────────────


# Placeholders this file is *supposed* to contain. Every statement uses these
# names deliberately; the operator substitutes real ones before running.
EXPECTED_PLACEHOLDERS = {"<runtime>", "<database>", "<generated-password>"}


def test_only_the_intended_placeholders_remain(sql: str) -> None:
    """A leftover placeholder is a script that fails when run.

    The file is a template, so placeholders in the statements are correct by
    design. What must not happen is a *new* placeholder appearing, or an expected
    one being spelled differently, because both mean the operator has a typo to
    find and the failure mode is a confusing psql error at run time.
    """
    found = set(re.findall(r"<[a-z_-]+>", sql))
    assert found == EXPECTED_PLACEHOLDERS, (
        f"placeholder set changed. expected {sorted(EXPECTED_PLACEHOLDERS)}, found {sorted(found)}"
    )


def test_every_statement_uses_a_placeholder_rather_than_a_hardcoded_name(sql: str) -> None:
    """Guards against a real name being committed into a shared artifact.

    This file is referenced from documentation that other projects read. A
    hardcoded application or database name would tie the procedure to one
    deployment, and would collide on any other instance.
    """
    hardcoded = re.findall(r"\b(?:acme|gestiket|tickets_db|provider_portal|catalog_db)\w*\b", sql, re.IGNORECASE)
    assert hardcoded == [], f"a concrete project name is baked into the template: {sorted(set(hardcoded))}"


def test_uses_a_psql_metacommand_for_the_database_switch(sql: str) -> None:
    """Step 5 must run against the target database, not against postgres.

    REVOKE/GRANT on SCHEMA are per-database. Running them against the wrong
    database silently succeeds and protects nothing, which is worse than failing.
    """
    assert "\\connect" in sql
    assert re.search(r"\\connect\s+<database>", sql), "the \\connect target is not the database placeholder"


# ── Two roles, and neither is privileged ───────────────────────────────────


def test_creates_a_runtime_and_a_migration_role(sql: str) -> None:
    """The runtime/migration split is the reason this file exists.

    A single owner role with GRANT ALL cannot answer "what damage can the
    running service do?" - its service credential can drop a column.
    """
    assert re.search(r"CREATE ROLE <runtime>_app\s+WITH LOGIN", sql)
    assert re.search(r"CREATE ROLE <runtime>_migr\s+WITH LOGIN", sql)


@pytest.mark.parametrize(
    "attribute",
    ["SUPERUSER", "CREATEDB", "CREATEROLE", "REPLICATION"],
)
def test_neither_role_is_created_with_a_privileged_attribute(sql: str, attribute: str) -> None:
    """A role created with these can escape the database boundary entirely."""
    for role in ("<runtime>_app", "<runtime>_migr"):
        match = re.search(rf"CREATE ROLE {role} WITH ([^;]+);", sql)
        assert match, f"{role} is not created"
        assert attribute not in match.group(1).upper(), f"{role} must not be created {attribute}"


def test_never_grants_all_privileges(sql: str) -> None:
    """GRANT ALL is what makes a service credential equivalent to an owner."""
    assert "GRANT ALL" not in sql.upper()


# ── The runtime role must not be able to change the schema ─────────────────


def test_runtime_role_does_not_receive_create_on_the_schema(sql: str) -> None:
    """CREATE on the schema is what allows CREATE TABLE.

    Without it the runtime role can use the schema but not add to it, which is
    the difference between a DML role and a DDL one.
    """
    grant = re.search(r"GRANT ([^;]+) ON SCHEMA public TO <runtime>_app;", sql)
    assert grant, "no schema grant for the runtime role"
    assert "CREATE" not in grant.group(1).upper()


def test_migration_role_does_receive_create_on_the_schema(sql: str) -> None:
    """Otherwise the migration role cannot do its job.

    Both halves are asserted deliberately: granting CREATE to the runtime role is
    the mistake this project is avoiding, and forgetting it for the migration
    role is an equally silent failure.
    """
    grant = re.search(r"GRANT ([^;]+) ON SCHEMA public TO <runtime>_migr;", sql)
    assert grant, "no schema grant for the migration role"
    assert "CREATE" in grant.group(1).upper()


def test_runtime_role_gets_dml_but_not_ddl_on_tables(sql: str) -> None:
    assert re.search(
        r"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO <runtime>_app;", sql
    )
    # No TRUNCATE, no REFERENCES, no TRIGGER: each is a way to damage data or
    # schema while holding only table-level grants.
    for extra in ("TRUNCATE", "REFERENCES", "TRIGGER"):
        assert extra not in sql.upper(), f"{extra} was granted to the runtime role"


def test_sequences_are_granted_to_the_runtime_role(sql: str) -> None:
    """Without USAGE on sequences, every serial insert fails at runtime.

    This was verified: a role with table-level DML but no sequence grant cannot
    call nextval, so inserts against a serial column fail.
    """
    assert re.search(
        r"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO <runtime>_app;", sql
    )


def test_default_privileges_cover_future_objects(sql: str) -> None:
    """ALTER DEFAULT PRIVILEGES is what keeps new tables from being ungranted."""
    assert sql.count("ALTER DEFAULT PRIVILEGES") >= 2
    assert "FOR ROLE <runtime>_migr" in sql


# ── Isolation from other applications on the shared instance ───────────────


def test_revokes_connect_from_public_on_system_databases(sql: str) -> None:
    """PUBLIC's default CONNECT is what lets any role reach any database.

    Verified on a disposable instance: a role granted nothing on a sibling
    database could still connect to it, because PUBLIC held CONNECT. Revoking
    from the role itself, as the sibling project's script does, does not fix
    this.
    """
    assert re.search(r"REVOKE CONNECT ON DATABASE postgres\s+FROM PUBLIC;", sql)
    assert re.search(r"REVOKE CONNECT ON DATABASE template1\s+FROM PUBLIC;", sql)


def test_public_is_revoked_on_the_target_database_too(sql: str) -> None:
    """Otherwise any role on the server can connect to this database.

    The sibling's script revokes on the system databases but not on its own, so
    its isolation claim does not hold for the database that actually matters.
    """
    assert re.search(r"REVOKE ALL ON DATABASE <database> FROM PUBLIC;", sql)
    # ...and the roles are granted CONNECT back explicitly, or the revocation
    # would lock the application out of its own database.
    assert re.search(r"GRANT CONNECT ON DATABASE <database> TO <runtime>_app, <runtime>_migr;", sql)


def test_schema_is_revoked_from_public(sql: str) -> None:
    """PostgreSQL 15 dropped this for new databases; older ones still carry it."""
    assert re.search(r"REVOKE ALL ON SCHEMA public FROM PUBLIC;", sql)


def test_server_wide_revoke_is_flagged_as_affecting_other_apps(script: str) -> None:
    """The REVOKE FROM PUBLIC affects every application on the instance.

    It has to be documented as a shared-instance change, so an operator reading
    this file for their own application realises they are changing something that
    is not theirs.
    """
    assert "SERVER-WIDE" in script.upper()
    assert "PUBLIC" in script


# ── No database creation, and no ownership by the application ──────────────


def test_never_creates_a_database(sql: str) -> None:
    """The schema of record is the only source of schema.

    A role that can CREATEDB, or a script that creates the database, creates a
    second way for the schema to exist - the drift that produced the deleted
    init.sql.
    """
    assert "CREATE DATABASE" not in sql.upper()
    assert "OWNER TO" not in sql.upper(), "the script transfers ownership, which defeats the grant model"


def test_no_literal_password_is_committed(sql: str) -> None:
    """Passwords belong in a gitignored .env, generated out of band."""
    for line in sql.splitlines():
        if "PASSWORD" in line.upper() and "CREATE ROLE" in line.upper():
            assert "<generated-password>" in line, f"a literal password is committed: {line!r}"


# ── The README is the operator's contract ──────────────────────────────────


def test_readme_states_the_execution_order() -> None:
    """Order matters and is easy to get wrong.

    Roles must be created after the schema, because the grants apply to existing
    objects and ALTER DEFAULT PRIVILEGES only covers later ones.
    """
    readme = PROVISION_README.read_text(encoding="utf-8")
    create_db = readme.index("Create the database")
    load_schema = readme.index("Load the schema of record")
    create_roles = readme.index("Create the roles and grant privileges")
    assert create_db < load_schema < create_roles


def test_readme_forbids_automated_provisioning() -> None:
    """A shared instance's credentials must not be created by compose up."""
    readme = PROVISION_README.read_text(encoding="utf-8")
    assert "docker compose up" in readme
    assert "never executed by" in readme.lower() or "never executed" in readme.lower()


def test_readme_documents_the_verification_matrix() -> None:
    """The file ships with checks; the README says which results to expect."""
    readme = PROVISION_README.read_text(encoding="utf-8")
    for check in ("CREATE TABLE", "DROP TABLE", "ALTER TABLE", "SELECT"):
        assert check in readme
    assert "fails" in readme and "succeeds" in readme
