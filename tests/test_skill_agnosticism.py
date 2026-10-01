"""Guards that the shared skill stays agnostic to stack, business, and namespaces.

The deployment skill is read by every application in the estate: different stacks,
different schemas, different credentials. Anything concrete that leaks into the
shared text is wrong in at least one of them, and a container or database name
copied from one project into another is how two applications end up pointing at
each other's data.

These are static checks over the skill's own text. They do not run a deployment,
they just keep the doctrine portable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "ai-specs" / "skills" / "deploying-backend-vps" / "SKILL.md"
HARNESS = Path(__file__).resolve().parents[1] / "ai-specs" / "harness-ia.md"

# Fenced code blocks are excluded from the prose checks below: a command example
# may legitimately mention a tool, and that is the point of an example.
FENCED_BLOCK = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)

# Markdown table rows are not prose: splitting them into "sentences" produces
# fragments like "| Create tables | yes |", which are not normative statements.
TABLE_ROW = re.compile(r"^\|.*$", re.MULTILINE)

# Names belonging to one deployment of this estate. A shared skill must not name
# them; the per-project instance under infra/ is where they belong.
NAMESPACES = [
    "postgres-gci",
    "minio-acme",
    "db_gestiket",
    "gestiket",
    "catalog_db",
    "provider_portal",
    "app-tickets",
]

# Business vocabulary from one application's domain.
BUSINESS_WORDS = [
    "ticket",
    "maintenance",
    "worksheet",
    "spares",
    "preliquidated",
    "holidays",
    "fsm_users",
    "token_blacklist",
]

# A tool named in prose is a leak only if it is presented as *the* mechanism
# rather than as one option, so these are counted rather than banned outright.
TOOLS = ["alembic", "prisma", "alembic", "sqlalchemy", "django", "flyway", "liquibase"]


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(skill_text: str) -> str:
    """The skill's narrative prose: no code blocks, no table rows.

    Table rows are excluded for the same reason code blocks are. A row like
    "| Create the database | no | no | no |" is a lookup, not an instruction, and
    treating it as a sentence produces false positives that would push someone to
    reword a correct table.
    """
    return TABLE_ROW.sub("", FENCED_BLOCK.sub("", skill_text))


@pytest.fixture(scope="module")
def tables(skill_text: str) -> str:
    """Markdown table rows only."""
    return "\n".join(TABLE_ROW.findall(skill_text))


# ── Namespaces: no deployment-specific identifiers in shared doctrine ───────


@pytest.mark.parametrize("name", NAMESPACES)
def test_no_deployment_namespace_leaks_into_the_skill(skill_text: str, name: str) -> None:
    """A concrete container or database name is wrong in every other project.

    The shared skill is read by applications that have never heard of this
    instance's container names. If one of them copied a command containing a
    foreign name, it would target the wrong server, and on a shared estate that
    is a cross-tenant mistake rather than a typo.
    """
    assert name not in skill_text, f"'{name}' is a deployment-specific name and must stay in infra/"


@pytest.mark.parametrize("name", NAMESPACES)
def test_no_namespace_leak_in_the_harness_map(name: str) -> None:
    """The harness map describes how doctrine is shared, so it must be generic too."""
    text = HARNESS.read_text(encoding="utf-8")
    assert name not in text, f"'{name}' is deployment-specific and does not belong in the harness map"


@pytest.mark.parametrize("port", ["5435", "9000", "9001", "8443"])
def test_no_hardcoded_ports_in_prose(prose: str, port: str) -> None:
    """Ports differ per deployment, and a wrong one in a shared command is harmful.

    Command examples legitimately show a port; the surrounding prose must not
    instruct anyone to use one.
    """
    assert port not in prose, f"port {port} is deployment-specific and belongs in infra/"


# ── Business vocabulary: the skill serves several domains ──────────────────


@pytest.mark.parametrize("word", BUSINESS_WORDS)
def test_no_single_domain_vocabulary_in_prose(prose: str, word: str) -> None:
    """The skill is shared across unrelated businesses.

    Domain words imply the reader runs this kind of application, which is the
    failure this guard exists to prevent: an estate where one app's vocabulary
    silently becomes everyone's mental model.
    """
    occurrences = re.findall(rf"\b{re.escape(word)}\w*\b", prose, re.IGNORECASE)
    assert not occurrences, f"business word '{word}' appears {len(occurrences)}x in the shared skill's prose"


# ── Stack: the doctrine must be stated independently of any tool ───────────


def test_prose_does_not_prescribe_a_single_tool(prose: str) -> None:
    """Tool names belong in the adapter table and in examples, not in the rules.

    The rules have to be readable by a project using a tool this skill has never
    heard of. Naming one tool in a normative sentence makes the rule look
    inapplicable to everyone else.
    """
    for tool in ("alembic", "prisma"):
        for sentence in re.split(r"(?<=[.!])\s+", prose):
            if re.search(rf"\b{tool}\b", sentence, re.IGNORECASE):
                assert not re.search(
                    r"\b(must|never|always|do not|should)\b", sentence, re.IGNORECASE
                ), f"a normative sentence names one stack's tool: {sentence.strip()[:120]!r}"


def test_keeps_a_tool_independent_adapter_table(skill_text: str) -> None:
    """The adapter table is how per-stack specifics stay available without leaking.

    Removing it would either force the rules to name a tool or lose the guidance
    for stacks the skill does not target, so it is asserted explicitly.
    """
    assert "Adapter table" in skill_text
    table = skill_text.split("### Adapter table", 1)[1].split("\n## ", 1)[0]
    # At least two stack columns, so it is genuinely a comparison.
    header = [line for line in table.splitlines() if line.strip().startswith("|")]
    assert header, "the adapter table has no rows"
    assert header[0].count("|") >= 4, "the adapter table covers fewer than two stacks"


def test_adapter_table_has_a_fallback_column(skill_text: str) -> None:
    """A stack the skill does not know about must still have an answer.

    The estate will gain a project whose migration tool is not in this table, and
    the table should degrade to "here is how to reason about it" rather than
    giving that project nothing.
    """
    table = skill_text.split("### Adapter table", 1)[1].split("\n## ", 1)[0]
    header = next(line for line in table.splitlines() if line.strip().startswith("|"))
    assert "no schema tool" in header.lower(), (
        f"the adapter table has no column for a stack this skill does not target: {header!r}"
    )


def test_no_orm_prescription_in_the_schema_of_record_row(skill_text: str) -> None:
    """The 'schema of record' row must defer to the project's actual stack.

    A skill that says 'the schema of record is the model file' pushes a project
    whose tool was adopted late into generating from stale models, which is the
    exact failure the skill documents elsewhere.
    """
    table = skill_text.split("### Adapter table", 1)[1].split("\n## ", 1)[0]
    table_rows = [line for line in table.splitlines() if line.strip().startswith("|")]
    rows = [line for line in table_rows if "schema of record" in line.lower()]
    assert rows, "the adapter table has no schema-of-record row"
    for line in rows:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        # The row must offer a different answer per stack shape, rather than one
        # artifact named unconditionally. Identical cells mean it prescribes.
        assert len(set(cells)) > 1, (
            f"the schema-of-record row gives one answer for every stack, which prescribes: {line.strip()!r}"
        )
        # And it must warn against inferring a schema file from stale models,
        # which is the failure the surrounding prose documents.
        assert "baseline" in line.lower() or "history" in line.lower() or "hand" in line.lower()


# ── The two new doctrine points, present and stack-agnostic ────────────────


def test_documents_public_privilege_isolation(prose: str) -> None:
    """Every role inherits CONNECT from PUBLIC, so role-level revokes do not isolate.

    This is the single most load-bearing provision step on a shared instance, and
    the non-obvious one: revoking from your own role changes nothing.

    The earlier version of this guard required the word "server-wide" and so
    required the wrong claim. REVOKE is per database and never was server-wide;
    asserting that it was baked the misconception into shared doctrine that other
    projects were told to follow.
    """
    lowered = prose.lower()
    assert "PUBLIC" in prose
    assert "inherit" in lowered or "inherits" in lowered
    assert "per database" in lowered, "REVOKE is per database, and that is the trap"
    assert "pg_hba" in lowered, "the mechanism that does enforce it should be named"


def test_recommends_pg_hba_over_revoke_from_public(prose: str) -> None:
    """The enforcement that works, and the one that only appears to.

    `REVOKE CONNECT ... FROM PUBLIC` is the instinctive move and it is a
    different, smaller thing than the instinct expects. `pg_hba.conf` is evaluated
    before any SQL, applies to every database at once, and is scoped to one role.
    A reader following this skill has to be told which one is load-bearing.
    """
    lowered = prose.lower()
    assert "host-based" in lowered or "host based" in lowered
    assert "first-match" in lowered or "first match" in lowered
    assert "reload" in lowered, "restarting the server would drop other tenants' connections"
    assert "reject" in lowered, "the deny line should be shown, not described"


def test_warns_against_a_second_migration_role(skill_text: str) -> None:
    """A DDL role that cannot do DDL is a trap someone will fall into again.

    Without ownership, `GRANT CREATE ON SCHEMA` permits creating new objects and
    nothing else; a test that alters a table the role just created appears to
    prove otherwise. The skill has to warn about the test as well as the design,
    because the test is what makes people reinstate the role.
    """
    lowered = skill_text.lower()
    assert "migration" in lowered
    for phrase in ("ownership", "create"):
        assert phrase in lowered
    assert "just created" in lowered or "just created it" in lowered, (
        "the flattering test should be named, since it is what people rely on"
    )


def test_documents_the_sequence_grant_trap(prose: str) -> None:
    """A DML role without a sequence grant fails late, on every serial insert.

    Omitting it looks fine until the first write, and the error does not mention
    provisioning.
    """
    lowered = prose.lower()
    assert "sequence" in lowered
    assert "nextval" in lowered, "the concrete failure mode should be named"


def test_documents_the_deferrable_trap(prose: str) -> None:
    """The obvious fix for a self-referencing load silently mutates the schema.

    Someone will reach for it, and it will work, which is what makes it dangerous.
    """
    lowered = prose.lower()
    assert "deferrable" in lowered
    assert "staging" in lowered, "the safe alternative should be named alongside the trap"


def test_seed_is_demoted_from_a_deployment_step(prose: str) -> None:
    """No deploy should run a seeder.

    Stating the seeder is not a deployment step is what keeps it out of a compose
    file, which is where it otherwise ends up.
    """
    assert "not a deployment step" in prose.lower()
    assert "allowlist" in prose.lower(), "the filename-to-table boundary should be named"


def test_provisioning_verification_is_asserted_not_assumed(skill_text: str) -> None:
    """Capability checks, not a catalog listing.

    Listing databases proves nothing, because every role can see the catalog. The
    concrete privilege attributes belong in a runnable example, so this scans the
    whole document rather than the prose.
    """
    lowered = skill_text.lower()
    assert "verify the boundary" in lowered or "assert the" in lowered
    for attribute in ("rolsuper", "rolcreatedb", "rolcreaterole"):
        assert attribute in lowered, f"the privilege attribute {attribute} should be named"
    assert "tableowner" in lowered, "the ownership check should be shown, not just described"
