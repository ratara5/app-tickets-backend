"""Guards for the database provisioning script.

The script is a Plane 1 (admin, one-time) artifact, run by hand. It cannot be
tested at runtime in CI because there is no database, and because running it
would create roles on a shared instance. What is asserted here is that the
privilege boundaries it claims to establish cannot be quietly removed: the grants
and the revokes are the whole point of the file, and a well-meaning edit that
drops one of them fails a test rather than shipping.

The behavioural matrix was established against a disposable PostgreSQL instance:
the role could SELECT, INSERT and use sequences; CREATE TABLE, DROP TABLE,
ALTER TABLE and CREATE INDEX were all denied; and the role could not connect to
another application's database once the pg_hba.conf rule was in place.

Two of these guards exist because the first version of the file was wrong and the
tests did not catch it. See test_no_migration_role_is_provisioned and
test_ownership_is_never_transferred.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROVISION_DIR = Path(__file__).resolve().parents[1] / "infra" / "provision"
PROVISION_SQL = PROVISION_DIR / "001-create-application-roles.sql"
PROVISION_README = PROVISION_DIR / "README.md"

# Comments are stripped for the grant assertions: the file documents the
# privileges it withholds as prominently as the ones it grants, so a substring
# check over the raw text would pass on prose alone.
LINE_COMMENT = re.compile(r"^\s*--.*$", re.MULTILINE)

RUNTIME_ROLE = "<runtime>_app"


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
EXPECTED_PLACEHOLDERS = {"<runtime>", "<database>", "<generated-password>", "<admin>"}


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


# ── Exactly one role, and it is not privileged ─────────────────────────────


def test_creates_exactly_one_role(sql: str) -> None:
    """The runtime role, and nothing else."""
    created = re.findall(r"CREATE ROLE (\S+)", sql)
    assert created == [RUNTIME_ROLE], f"expected only {RUNTIME_ROLE}, script creates {created}"


def test_no_migration_role_is_provisioned(sql: str) -> None:
    """A DDL role cannot do DDL here, and making it able to would defeat the point.

    This is a correction, not a style preference. The previous version created
    `<runtime>_migr` with CREATE on the schema. CREATE permits creating new
    objects; ALTER and DROP on existing ones need ownership, which is never
    granted. So that role could create an empty table and could not alter a real
    one. The test that seemed to prove otherwise had only exercised a table the
    role had just created.

    The two ways to fix it are both worse: transferring table ownership to the
    role puts the schema-changing credential in charge of the data, and granting
    the role to the runtime role hands every DDL capability to the service
    credential, which is the whole thing the split was meant to prevent.

    Checked against executable SQL, not the file text: both artifacts discuss
    the removed role in prose, on purpose, so that the next reader understands
    why it is absent instead of adding it back.
    """
    assert "_migr" not in sql, "a migration role has been reintroduced into the executable SQL"
    for target in re.findall(r"(?:GRANT|REVOKE|ALTER) [^;]+ TO ([^;]+);", sql):
        assert "_migr" not in target, f"a privilege is being granted to a migration role: {target!r}"


def test_the_readme_says_why_there_is_no_migration_role() -> None:
    """Someone will read this file and think a DDL role is missing.

    The reason has to be recorded where they will meet it, with the mechanism,
    or the next person adds one back believing they are closing a gap. It is a
    separate assertion from the one above because prose is the thing being
    checked, not SQL.
    """
    readme = PROVISION_README.read_text(encoding="utf-8").lower()
    assert "no migration role" in readme


def test_ownership_is_never_transferred(sql: str) -> None:
    """A grantee is not an owner, and that asymmetry is the whole design.

    An owner can drop its own objects and reshape the schema. The moment
    ownership moves to any application credential, the grant model above it is
    decoration, and the file's own comment claiming otherwise becomes false.
    """
    assert "OWNER TO" not in sql.upper(), "the script transfers ownership, which defeats the grant model"


def test_no_statement_moves_or_shares_ownership(sql: str) -> None:
    """`REASSIGN OWNED` and `ALTER ... OWNER TO` are the two ways this happens by
    accident during a later edit, and `SET ROLE` is how a session borrows one.

    Checked against executable SQL only: the file's own header has to be able to
    name these statements in order to say it does not perform them.
    """
    for pattern in ("REASSIGN OWNED", "OWNER TO", "SET ROLE"):
        assert pattern not in sql.upper(), f"{pattern} would move or share ownership"


@pytest.mark.parametrize(
    "attribute",
    ["SUPERUSER", "CREATEDB", "CREATEROLE", "REPLICATION"],
)
def test_the_role_is_not_created_with_a_privileged_attribute(sql: str, attribute: str) -> None:
    """A role created with these can escape the database boundary entirely.

    Asserted as a standalone token, not a substring. `NOSUPERUSER` contains
    `SUPERUSER`, so a naive `attribute not in options` check passes over the
    very declaration it is meant to catch — which is why the previous version of
    this test never fired against a role that had no attributes spelled out at
    all, and would not have fired against one that had.
    """
    match = re.search(rf"CREATE ROLE {RUNTIME_ROLE} WITH ([^;]+);", sql, re.S)
    assert match, f"{RUNTIME_ROLE} is not created"
    options = match.group(1).upper()
    assert not re.search(rf"(?<!NO)\b{attribute}\b", options), f"{RUNTIME_ROLE} must not be created {attribute}"
    # And the denial must be explicit rather than left to a server default that
    # a hardened postgresql.conf could change underneath this file.
    assert f"NO{attribute}" in options, f"NO{attribute} is not stated explicitly for {RUNTIME_ROLE}"


def test_noinherit_is_set_explicitly(sql: str) -> None:
    """A role that cannot inherit memberships cannot be widened later by accident.

    Named explicitly rather than left to the server default, so a hardened
    postgresql.conf cannot silently change what this role is.
    """
    match = re.search(rf"CREATE ROLE {RUNTIME_ROLE} WITH ([^;]+);", sql, re.S)
    assert match
    assert "NOINHERIT" in match.group(1).upper()


def test_never_grants_all_privileges(sql: str) -> None:
    """GRANT ALL is what makes a service credential equivalent to an owner."""
    assert "GRANT ALL" not in sql.upper()


# ── The role must not be able to change the schema ─────────────────────────


def test_the_role_does_not_receive_create_on_the_schema(sql: str) -> None:
    """CREATE on the schema is what allows CREATE TABLE and CREATE INDEX."""
    grant = re.search(rf"GRANT ([^;]+) ON SCHEMA public TO {RUNTIME_ROLE};", sql)
    assert grant, "no schema grant for the runtime role"
    assert "CREATE" not in grant.group(1).upper()


def test_no_role_receives_create_on_the_schema(sql: str) -> None:
    """Not the runtime role, and not anyone else this script creates.

    A second role with CREATE was the original defect. This asserts the absence
    of the grant generally, so reintroducing it under a different name still
    fails.
    """
    for grant in re.findall(r"GRANT ([^;]+) ON SCHEMA public TO ([^;]+);", sql):
        assert "CREATE" not in grant[0].upper(), f"CREATE on schema granted to {grant[1]}"


def test_the_role_gets_dml_but_not_ddl_on_tables(sql: str) -> None:
    assert re.search(
        rf"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RUNTIME_ROLE};", sql
    )
    # No TRUNCATE, no REFERENCES, no TRIGGER: each is a way to damage data or
    # schema while holding only table-level grants.
    for extra in ("TRUNCATE", "REFERENCES", "TRIGGER"):
        assert extra not in sql.upper(), f"{extra} was granted to the runtime role"


def test_sequences_are_granted_to_the_role(sql: str) -> None:
    """Without USAGE on sequences, every serial insert fails at runtime.

    This was verified: a role with table-level DML but no sequence grant cannot
    call nextval, so inserts against a serial column fail.
    """
    assert re.search(rf"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME_ROLE};", sql)


def test_default_privileges_name_the_owning_role_not_the_app_role(sql: str) -> None:
    """ALTER DEFAULT PRIVILEGES is a statement about future objects created BY a role.

    Naming the application role here produces a script that reads correctly and
    grants nothing, because the application role never creates the objects. The
    owner is the administrator who loads the schema of record.
    """
    matches = re.findall(r"ALTER DEFAULT PRIVILEGES FOR ROLE (\S+)", sql)
    assert len(matches) >= 2, "expected table and sequence default privileges"
    for role in matches:
        assert role == "<admin>", (
            f"ALTER DEFAULT PRIVILEGES names {role!r}. It must name the role that "
            f"creates the objects, not {RUNTIME_ROLE}."
        )


# ── Isolation from other applications on the shared instance ───────────────


def test_does_not_revoke_connect_from_public_on_system_databases(sql: str) -> None:
    """The previous version did this, and it did not achieve isolation.

    REVOKE is per database. It never made the server-wide, it made that one
    database unreachable to tenants relying on the PUBLIC default, and it left
    every sibling database exactly as reachable as before. It also broke other
    applications' code from a change this project had no business making.
    """
    assert not re.search(r"REVOKE CONNECT ON DATABASE (?:postgres|template1)\s+FROM PUBLIC;", sql), (
        "revoking PUBLIC CONNECT on system databases does not isolate this role "
        "and affects other tenants. Use pg_hba.conf instead."
    )


def test_revokes_public_on_the_target_database(sql: str) -> None:
    """Otherwise any role on the server can connect to this database."""
    assert re.search(r"REVOKE ALL ON DATABASE <database> FROM PUBLIC;", sql)
    # ...and the role is granted CONNECT back explicitly, or the revocation
    # would lock the application out of its own database.
    assert re.search(rf"GRANT CONNECT ON DATABASE <database> TO {RUNTIME_ROLE};", sql)


def test_schema_is_revoked_from_public(sql: str) -> None:
    """PostgreSQL 15 dropped this for new databases; older ones still carry it."""
    assert re.search(r"REVOKE ALL ON SCHEMA public FROM PUBLIC;", sql)


def test_pg_hba_is_documented_with_allow_before_deny(script: str) -> None:
    """pg_hba.conf is first-match, so the order in the file is the whole policy.

    Reversed, the deny-all matches first and the role cannot reach its own
    database, which looks like a broken grant rather than a broken rule.
    """
    allow = re.search(r"host\s+<database>\s+<runtime>_app\s+<app-cidr>\s+scram-sha-256", script)
    deny = re.search(r"host\s+all\s+<runtime>_app\s+0\.0\.0\.0/0\s+reject", script)
    assert allow, "no allow line for the role on its own database"
    assert deny, "no deny-all line for the role on every other database"
    assert allow.start() < deny.start(), "the deny line precedes the allow line; pg_hba is first-match"


def test_pg_hba_step_tells_the_operator_to_reload_not_restart(script: str) -> None:
    """A restart drops in-flight connections for every tenant on the instance."""
    assert "pg_reload_conf" in script
    assert "restart" in script.lower()
    assert "Reload" in script or "reload" in script


def test_isolation_is_documented_as_per_database_not_server_wide(script: str) -> None:
    """The word SERVER-WIDE was wrong, and it is the kind of wrong that misleads.

    It cannot simply be banned, because the file has to be able to name the
    misconception in order to correct it. So every line that uses it must also
    deny it, which is what stops a later edit from reasserting the claim while
    leaving the correction nearby.
    """
    negations = ("not ", "never", "does not", "isn't", "is not")
    for line in script.splitlines():
        if "server-wide" in line.lower():
            assert any(word in line.lower() for word in negations), (
                f"the file asserts the REVOKE is server-wide: {line.strip()!r}"
            )
    assert "per database" in script.lower()


def test_the_sql_file_does_not_claim_to_enforce_reachability_alone(script: str) -> None:
    """It cannot. The boundary is in pg_hba.conf, and the file must say so.

    Without this, an operator reads the REVOKEs, sees no GRANT-style escape
    hatch, and concludes the role is isolated from the other tenants.
    """
    assert "pg_hba" in script
    assert "cannot be done from SQL" in script


# ── No database creation ───────────────────────────────────────────────────


def test_never_creates_a_database(sql: str) -> None:
    """The schema of record is the only source of schema.

    A role that can CREATEDB, or a script that creates the database, creates a
    second way for the schema to exist - the drift that produced the deleted
    init.sql.
    """
    assert "CREATE DATABASE" not in sql.upper()


def test_the_ownership_check_uses_a_catalog_that_has_the_column(script: str) -> None:
    """The verification queries are only worth having if they actually run.

    The previous version asked `information_schema.tables` for `tableowner`,
    which does not exist. The query errored, the operator saw a failure in a
    check they were told was mandatory, and the one that mattered most - does the
    application role own anything - was never established. The pg_ catalog is
    where ownership actually lives.
    """
    check = re.search(r"SELECT tablename FROM pg_tables.*?;", script, re.S)
    assert check, "the ownership verification query is missing"
    assert "tableowner" in check.group(0)
    assert "information_schema.tables" not in check.group(0), (
        "information_schema.tables has no tableowner column; use pg_tables"
    )


def test_the_verification_queries_are_marked_as_never_executed(script: str) -> None:
    """They are checks, not steps.

    A verification block that is actually executed by `psql -f` would fail the
    run on the first permission check, which is the intended DDL-failure result
    but the wrong place to discover it.
    """
    body = script.split("Verify, do not assume", 1)[1]
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("SELECT", "CREATE ", "DROP ", "ALTER ", "INSERT ", "psql ")):
            assert line.startswith("--"), f"verification statement is not commented out: {stripped!r}"


def test_no_literal_password_is_committed(sql: str) -> None:
    """Passwords belong in a gitignored .env, generated out of band."""
    for line in sql.splitlines():
        if "PASSWORD" in line.upper() and "CREATE ROLE" in line.upper():
            assert "<generated-password>" in line, f"a literal password is committed: {line!r}"


# ── The README is the operator's contract ──────────────────────────────────


def test_readme_states_the_execution_order() -> None:
    """Order matters and is easy to get wrong.

    Roles must be created after the schema, because the grants apply to existing
    objects and ALTER DEFAULT PRIVILEGES only covers later ones. The network rule
    goes last because a role with no privileges is harmless until reachable.
    """
    readme = PROVISION_README.read_text(encoding="utf-8")
    create_db = readme.index("Create the database")
    load_schema = readme.index("Load the schema of record")
    create_roles = readme.index("Create the roles and grant privileges")
    pg_hba = readme.index("pg_hba.conf` rule")
    assert create_db < load_schema < create_roles < pg_hba


def test_readme_forbids_automated_provisioning() -> None:
    """A shared instance's credentials must not be created by compose up."""
    readme = PROVISION_README.read_text(encoding="utf-8")
    assert "docker compose up" in readme
    assert "never executed by" in readme.lower() or "never executed" in readme.lower()


def test_readme_documents_the_verification_matrix() -> None:
    """The file ships with checks; the README says which results to expect."""
    readme = PROVISION_README.read_text(encoding="utf-8")
    for check in ("CREATE TABLE", "DROP TABLE", "ALTER TABLE", "CREATE INDEX", "SELECT"):
        assert check in readme
    assert "fails" in readme and "succeeds" in readme


def test_readme_explains_why_the_migration_role_was_removed() -> None:
    """Someone will read this file and think a DDL role is missing.

    The reason has to be here, with the mechanism, or the next person adds one
    back believing they are closing a gap.
    """
    readme = PROVISION_README.read_text(encoding="utf-8").lower()
    assert "no migration role" in readme
    assert "ownership" in readme
    assert "create" in readme and "alter" in readme and "drop" in readme


def test_readme_says_the_final_check_must_come_from_another_host() -> None:
    """A connection that never leaves the container proves less than it looks.

    The deny rule is address-scoped. Verifying over loopback exercises a
    different code path than the one a real attacker or a misconfigured peer
    would take.
    """
    readme = PROVISION_README.read_text(encoding="utf-8")
    assert "different host" in readme.lower()
