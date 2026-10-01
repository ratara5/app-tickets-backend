"""Guards that the shared skills and personas stay agnostic to stack, business, and
namespaces.

The cross-project skills are read by every application in the estate: different
stacks, different schemas, different credentials. Anything concrete that leaks
into the shared text is wrong in at least one of them, and a container or database
name copied from one project into another is how two applications end up pointing
at each other's data.

These are static checks over the shared text. They do not run a deployment, they
just keep the doctrine portable.

Three groups of checks live here.

**Shared doctrine** (`CROSS_PROJECT_DOCTRINE`) applies to everything marked canonical
and cross-project in `openspec/config.yaml`: the skills in `CROSS_PROJECT_SKILLS` and
the personas in `CROSS_PROJECT_AGENTS`. It asks two questions of all of them: does a
concrete identifier leak in, and does a rule prescribe one stack's tool? The personas
were added to this list when the first estate-wide persona was written. Before that,
the guarded subject list was skills only, which meant the next piece of cross-project
text would have been the thing that landed in the unguarded folder.

**Persona adoption** (the description guards) applies to the personas only. A persona
is chosen by matching its description against the request, so a description that states
what the persona does instead of when it applies makes the persona invisible, and two
descriptions that overlap make the choice arbitrary.

**Estate deployment doctrine** (the remaining tests) applies only to
`deploying-backend-vps`, which is genuinely about one PostgreSQL and one MinIO
shared by several applications. Its checks are far more specific — role
privileges, migration sequences, the health of the `pg_hba` file — and they have
no meaning for a skill about prompt rewriting or backlog triage.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SPECS = REPO_ROOT / "ai-specs"
SKILLS = AI_SPECS / "skills"
AGENTS = AI_SPECS / "agents"
HARNESS = AI_SPECS / "harness-ia.md"

# Skills declared canonical and cross-project in `openspec/config.yaml`. Each is
# read by applications that share nothing but this estate, so each must survive
# being applied to a stack it was not written for.
CROSS_PROJECT_SKILLS = [
    "deploying-backend-vps",
    "defining-project-quality-gates",
    "dev-environment-parity",
    "observability-and-slo",
    "promoting-a-build",
    "triaging-spec-debt",
    "verifying-a-deployment",
]

# Personas declared canonical and cross-project in `openspec/config.yaml`. The
# guards that apply to a skill apply to these for the same reason: a persona
# adopted by an agent in another application is read by that application's
# stack, not by the one it was written for. They were unguarded until an
# estate-wide persona was added, which is precisely the moment the hole becomes
# easy to fill.
CROSS_PROJECT_AGENTS = [
    "infrastructure-developer",
]

# Everything that carries estate-wide doctrine, guarded identically. A check that
# covers skills and not personas is a check whose subject list silently decides
# which files may leak.
CROSS_PROJECT_DOCTRINE = CROSS_PROJECT_SKILLS + CROSS_PROJECT_AGENTS

DEPLOYMENT_SKILL = "deploying-backend-vps"

# The files that carry the rule for a dependency this project does not own. Guarded
# separately from CROSS_PROJECT_DOCTRINE because the failure being guarded here is a
# *reasoning* failure rather than a leak: a prohibition stated without its scope, which
# a reader then applies to the case it was not written for.
SHARED_DEPENDENCY_DOCTRINE = [
    "dev-environment-parity",
    "infrastructure-developer",
]

# Sentences that were in the first version of the shared-dependency doctrine and were
# wrong without a scope. They are listed verbatim rather than described, because the
# defect was that they read as universal rules — a paraphrase would reintroduce the
# same claim in a form this guard cannot see.
UNSCOPED_PROHIBITIONS = [
    "never attach to a shared network",
    "never attach a local stack to a network shared",
    "a local environment is a private one",
    "its own network, joined only by local services",
    "join the shared network for name resolution",
    "must not be able to reach shared state",
]

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

# Domain nouns from one application's business, restricted to terms with no
# legitimate generic use.
#
# `ticket`, `maintenance` and `holidays` used to be on this list and were removed.
# Each is ordinary English: the estate skill says "never paste a real secret into
# a runbook, ticket or commit", where `ticket` is a work item and nothing to do
# with the Ticket table. A static check cannot tell that use from a leak, so the
# term had to go. Keeping it would have meant either a false failure or a
# reworded sentence that is worse English than what it replaced, and either way
# the guard taught someone to write around it.
BUSINESS_NOUNS = [
    "worksheet",
    "spares",
    "preliquidated",
    "fsm_users",
    "token_blacklist",
]

# Skills whose subject overlaps the shared PostgreSQL/MinIO instance, and which
# therefore have something to delegate. The others — prompt rewriting, backlog
# triage, observability, local setup, quality gates — have no tenancy surface at
# all, and asking them to point at a deployment skill would add a link that
# teaches nothing.
RELEASE_SKILLS = [
    "promoting-a-build",
    "verifying-a-deployment",
]

# Facts that belong to one estate's provisioning. A shared skill must not restate
# them, whatever it says it is about: the moment two skills hold a copy of a
# provisioning rule, one of them is the copy nobody updates.
ESTATE_SPECIFICS = [
    "pg_hba",
    "rolsuper",
    "rolcreatedb",
    "nextval",
    "tableowner",
    "deferrable",
]

# Tools that bind a rule to one stack. `docker` and `make` are absent on purpose:
# a container runtime and a task runner are the substrate almost every stack in
# this estate already shares, so naming them does not make a rule inapplicable
# elsewhere. A migration tool or an orchestrator does.
STACK_BOUND_TOOLS = [
    "alembic",
    "prisma",
    "sqlalchemy",
    "django",
    "flyway",
    "liquibase",
    "terraform",
    "helm",
]

# Normalisation words that make a sentence normative. A rule that constrains
# behaviour is what must not name a tool.
NORMATIVE = r"\b(must|never|always|do not|should|require[sd]?|shall)\b"


def read(doctrine: str) -> str:
    """A skill's own text plus its references, or a persona's single file.

    References are part of what the reader loads, so a leak in a reference is just
    as wrong as a leak in the body, and checking only the body would let it through
    by relocation. A persona has no reference folder, so it is read directly.
    """
    path = AGENTS / f"{doctrine}.md" if doctrine in CROSS_PROJECT_AGENTS else SKILLS / doctrine
    if path.is_file():
        return path.read_text(encoding="utf-8")
    parts = [p.read_text(encoding="utf-8") for p in sorted(path.rglob("*.md"))]
    assert parts, f"{doctrine} has no markdown to check"
    return "\n".join(parts)


def prose_of(doctrine: str) -> str:
    """The narrative prose: no code blocks, no table rows.

    Table rows are excluded for the same reason code blocks are. A row like
    "| Create the database | no | no | no |" is a lookup, not an instruction, and
    treating it as a sentence produces false positives that would push someone to
    reword a correct table.
    """
    return TABLE_ROW.sub("", FENCED_BLOCK.sub("", read(doctrine)))


def _sentence_offending_in(sentences: list[str], tool: str) -> str | None:
    """The first sentence that names `tool` normatively without an alternative.

    Naming several options in one sentence is how a skill stays portable: "the
    deploy layer (Compose, Swarm, Kubernetes, a PaaS) changes, the promotion
    discipline does not" mentions four platforms precisely so that none of them is
    prescribed. That must pass. Naming one tool in a normative sentence does not,
    because it makes the rule look inapplicable to everyone else.
    """
    pattern = rf"\b{re.escape(tool)}\b"
    for sentence in sentences:
        if not re.search(pattern, sentence, re.IGNORECASE):
            continue
        if not re.search(NORMATIVE, sentence, re.IGNORECASE):
            continue
        # A sentence offering a choice names more than one mechanism.
        others = {
            t for t in STACK_BOUND_TOOLS if re.search(rf"\b{t}\b", sentence, re.IGNORECASE)
        }
        if len(others) > 1:
            continue
        if re.search(r"\b(or|either|alternative|any of|whichever)\b", sentence, re.IGNORECASE):
            continue
        return sentence.strip()
    return None


# ── Shared doctrine: identifiers must not leak ──────────────────────────────


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
@pytest.mark.parametrize("name", NAMESPACES)
def test_no_estate_namespace_leaks_into_a_shared_skill(skill: str, name: str) -> None:
    """A concrete container or database name is wrong in every other project.

    A shared skill is read by applications that have never heard of this
    instance's container names. If one of them copied a command containing a
    foreign name, it would target the wrong server, and on a shared estate that
    is a cross-tenant mistake rather than a typo.
    """
    assert name not in read(skill), f"'{name}' is deployment-specific and must stay in infra/"


@pytest.mark.parametrize("name", NAMESPACES)
def test_no_namespace_leak_in_the_harness_map(name: str) -> None:
    """The harness map describes how doctrine is shared, so it must be generic too."""
    text = HARNESS.read_text(encoding="utf-8")
    assert name not in text, f"'{name}' is deployment-specific and does not belong in the harness map"


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
@pytest.mark.parametrize("word", BUSINESS_NOUNS)
def test_no_domain_vocabulary_in_a_shared_skill(skill: str, word: str) -> None:
    """The estate serves unrelated businesses.

    Domain nouns imply the reader runs this kind of application, which is the
    failure this guard exists to prevent: an estate where one app's vocabulary
    silently becomes everyone's mental model.
    """
    occurrences = re.findall(rf"\b{re.escape(word)}\w*\b", prose_of(skill), re.IGNORECASE)
    assert not occurrences, f"domain noun '{word}' appears {len(occurrences)}x in {skill}"


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
@pytest.mark.parametrize("port", ["5435", "9000", "9001", "8443"])
def test_no_hardcoded_ports_in_prose(skill: str, port: str) -> None:
    """Ports differ per deployment, and a wrong one in a shared command is harmful.

    Command examples legitimately show a port; the surrounding prose must not
    instruct anyone to use one.
    """
    assert port not in prose_of(skill), f"port {port} is deployment-specific and belongs in infra/"


# ── Shared doctrine: no rule may bind itself to one stack ──────────────────


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
def test_no_shared_skill_prescribes_a_single_stack_tool(skill: str) -> None:
    """A normative sentence must not name one stack's tool as the mechanism.

    Tool names belong in adapter tables and in examples, not in the rules. The
    rules have to be readable by a project using a tool these skills have never
    heard of, and a sentence that says "always run alembic upgrade head" is
    inapplicable — so it gets ignored — everywhere except one project.
    """
    sentences = re.split(r"(?<=[.!])\s+", prose_of(skill))
    for tool in STACK_BOUND_TOOLS:
        offending = _sentence_offending_in(sentences, tool)
        assert offending is None, f"{skill} names one stack's tool normatively: {offending[:160]!r}"


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
def test_shared_skill_declares_its_own_portability(skill: str) -> None:
    """Each shared skill must say, in its own text, that it is stack-agnostic.

    This is not decoration. A reader who does not know these skills are shared
    will reasonably treat a doctrine as written for this stack, and portability
    that is only documented in a central map is one refactor away from being
    invisible. The claim has to be where the reader meets it.

    The wording is free — any explicit statement qualifies — because the failure
    being guarded is the absence of the claim, not its phrasing.
    """
    prose = prose_of(skill).lower()
    claims = (
        "agnostic",
        "adapter table",
        "tool-independent",
        "independently of any tool",
        "independent of the tool",
        "per-stack",
        "whatever the tool",
        "no vendor",
        "not prescribe",
    )
    assert any(claim in prose for claim in claims), (
        f"{skill} does not state anywhere that its doctrine is portable across "
        "stacks, so a reader will assume it is written for this stack"
    )


@pytest.mark.parametrize("skill", RELEASE_SKILLS)
def test_release_skill_delegates_estate_provisioning_rather_than_inlining_it(skill: str) -> None:
    """A release skill must point at the estate skill, not restate it.

    Two copies of the same rule diverge, and the copy nobody updates is the one
    that gets followed. This is the failure the canonical/pointer rule in
    `docs/base-standards.md` §5 exists to prevent, applied to skill prose.
    """
    prose = prose_of(skill)
    signals = ("deploying-backend-vps", "estate-specific", "per-project instance")
    assert any(signal in prose for signal in signals), (
        f"{skill} governs release and therefore overlaps the shared instance, but "
        "never delegates the tenancy and provisioning specifics, so it will be "
        "tempted to state them"
    )


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
def test_estate_provisioning_facts_stay_in_the_estate_skill(skill: str) -> None:
    """Only the estate skill may hold the provisioning rules.

    This is the direct form of the delegation rule above: rather than checking
    that each skill admits it should delegate, it checks that none of them holds
    the facts. A skill that copies a rule and cites the estate skill is still two
    copies, and the citation is what makes the stale one look authoritative.
    """
    if skill == DEPLOYMENT_SKILL:
        pytest.skip("this is where they belong")
    text = read(skill).lower()
    found = [fact for fact in ESTATE_SPECIFICS if fact in text]
    assert not found, (
        f"{skill} restates estate provisioning facts ({', '.join(found)}); they belong "
        f"in the {DEPLOYMENT_SKILL} skill, which is their single source"
    )


@pytest.mark.parametrize("doctrine", SHARED_DEPENDENCY_DOCTRINE)
def test_shared_dependency_doctrine_distinguishes_consumer_from_provider(doctrine: str) -> None:
    """A rule for a dependency you do not own must be scoped by which side you are on.

    The first version of this doctrine read "a local environment must not reach shared
    state" and "never attach to a shared network", with no condition attached. Every
    consumer of a shared core applied it to the core it was meant to consume, and
    produced a private instance — which is a *different* system, so the local run
    exercised settings the deployment never would. The protection was real; the scope
    was missing.

    So the doctrine must name both sides. If it stops distinguishing them, the
    prohibition reappears as a universal rule, and the guard fails at the edit that
    drops the distinction rather than at the project that suffers from it.
    """
    prose = prose_of(doctrine).lower()
    missing = [side for side in ("consumer", "provider") if side not in prose]
    assert not missing, (
        f"{doctrine} governs a dependency this project does not own but never names "
        f"{' and '.join(missing)}, so its rules cannot be scoped to the side the "
        "reader is on and the prohibition applies to the consumer case as well"
    )


@pytest.mark.parametrize("doctrine", SHARED_DEPENDENCY_DOCTRINE)
def test_shared_dependency_doctrine_grants_the_consumers_join(doctrine: str) -> None:
    """A consumer must be told, positively, that joining the provider's network is expected.

    The failure this prevents is a correction that only removes a prohibition and never
    grants the alternative. A reader who is told what not to do, and not told what to do
    instead, keeps the old behaviour or invents a private stack to satisfy the letter of
    the rule. The grant has to be explicit and has to name the mechanism — declaring the
    network external — because "join it" without that reads as permission to create or
    rename it.
    """
    prose = prose_of(doctrine).lower()
    assert "external" in prose, (
        f"{doctrine} scopes its shared-dependency rules but never says that a consumer "
        "declares the provider's network external, so the grant is missing the part "
        "that keeps it from mutating a network it does not own"
    )


@pytest.mark.parametrize("doctrine", SHARED_DEPENDENCY_DOCTRINE)
def test_no_unscoped_prohibition_against_reaching_a_shared_dependency(doctrine: str) -> None:
    """The first draft's unscoped sentences must not come back.

    These are quoted verbatim from the version that produced private stacks in the
    projects the doctrine was written for. A description of the defect could be
    satisfied by a reworded sentence carrying the same claim, so the guard matches the
    text that was actually wrong.
    """
    prose = prose_of(doctrine).lower()
    found = [sentence for sentence in UNSCOPED_PROHIBITIONS if sentence in prose]
    assert not found, (
        f"{doctrine} contains an unscoped prohibition against reaching a shared "
        f"dependency ({'; '.join(found)}). Restate it as the rule for the provider "
        "side, and state what a consumer does instead"
    )


@pytest.mark.parametrize("skill", CROSS_PROJECT_DOCTRINE)
def test_shared_skill_has_an_input_and_an_output(skill: str) -> None:
    """Each shared skill states what it is given and what it produces.

    A shared skill is invoked by an agent that was not written by its author. If
    it does not say what it consumes or what it hands back, the invoking agent
    supplies its own guesses, and two agents apply the same doctrine
    inconsistently.
    """
    text = read(skill).lower()
    says_input = "**input**" in text or "input:" in text or "## input" in text
    says_output = any(
        marker in text
        for marker in ("**output**", "output:", "## output", "verification", "verify", "checklist", "anti-pattern")
    )
    assert says_input, f"{skill} does not state its input"
    assert says_output, f"{skill} does not state what it produces or how it is verified"


# ── Persona adoption: a description that matches nothing is never loaded ─────


@pytest.mark.parametrize("agent", CROSS_PROJECT_AGENTS)
def test_persona_description_states_the_condition_it_applies_to(agent: str) -> None:
    """A persona is chosen by its description, so the description must carry a trigger.

    The same rule the skill guards apply to `writing-skills` CSO: state the conditions
    under which this applies, not what it does. A persona described by its subject
    matter matches nothing at selection time and is never adopted, while the persona
    whose description happens to overlap it is adopted instead — so the failure is not
    an omission but a silent substitution.
    """
    text = read(agent)
    frontmatter = text.split("---", 2)[1]
    match = re.search(r"^description:\s*(.*?)(?=^\w|\Z)", frontmatter, re.MULTILINE | re.DOTALL)
    assert match, f"{agent} has no description in its frontmatter"
    description = " ".join(match.group(1).split())
    assert len(description) >= 200, (
        f"{agent} description is {len(description)} characters. It states what the "
        "persona does, not the conditions under which it applies, so selection has "
        "nothing to match on."
    )
    for placeholder in ("tbd", "todo", "task-focused", "a skill"):
        assert placeholder not in description.lower(), f"{agent} description contains {placeholder!r}"


@pytest.mark.parametrize("agent", CROSS_PROJECT_AGENTS)
def test_persona_names_what_it_delegates(agent: str) -> None:
    """A persona with an unbounded scope absorbs work that belongs to someone else.

    The hazard is concrete: a persona that both decides and implements overlaps the
    implementation persona for its stack, and a harness that picks between them by
    description match will choose at random. Naming the delegations is what keeps the
    two adjacent rather than competing, and it is also what stops doctrine owned by a
    skill from being restated here as a second copy.
    """
    text = read(agent).lower()
    assert "delegat" in text, (
        f"{agent} never names what it delegates. A persona with no stated boundary "
        "competes with the persona that owns the neighbouring work."
    )
    assert re.search(r"\b(owns|own:)\b", text), (
        f"{agent} does not state what it owns, so the boundary it delegates around is "
        "not stated either"
    )


# ── Estate deployment doctrine: specific to the shared PG/MinIO instance ────


@pytest.fixture(scope="module")
def deployment_skill_text() -> str:
    return read(DEPLOYMENT_SKILL)


@pytest.fixture(scope="module")
def deployment_prose() -> str:
    return prose_of(DEPLOYMENT_SKILL)


@pytest.fixture(scope="module")
def deployment_tables(deployment_skill_text: str) -> str:
    """Markdown table rows of the deployment skill only."""
    return "\n".join(TABLE_ROW.findall(deployment_skill_text))


@pytest.mark.parametrize("word", BUSINESS_NOUNS)
def test_no_single_domain_vocabulary_in_the_estate_skill(deployment_prose: str, word: str) -> None:
    """The same domain vocabulary check, applied to the estate skill itself."""
    occurrences = re.findall(rf"\b{re.escape(word)}\w*\b", deployment_prose, re.IGNORECASE)
    assert not occurrences, f"domain noun '{word}' appears {len(occurrences)}x in the estate skill's prose"


def test_keeps_a_tool_independent_adapter_table(deployment_skill_text: str) -> None:
    """The adapter table is how per-stack specifics stay available without leaking.

    Removing it would either force the rules to name a tool or lose the guidance
    for stacks the skill does not target, so it is asserted explicitly.
    """
    assert "Adapter table" in deployment_skill_text
    table = deployment_skill_text.split("### Adapter table", 1)[1].split("\n## ", 1)[0]
    # At least two stack columns, so it is genuinely a comparison.
    header = [line for line in table.splitlines() if line.strip().startswith("|")]
    assert header, "the adapter table has no rows"
    assert header[0].count("|") >= 4, "the adapter table covers fewer than two stacks"


def test_adapter_table_has_a_fallback_column(deployment_skill_text: str) -> None:
    """A stack the skill does not know about must still have an answer.

    The estate will gain a project whose migration tool is not in this table, and
    the table should degrade to "here is how to reason about it" rather than
    giving that project nothing.
    """
    table = deployment_skill_text.split("### Adapter table", 1)[1].split("\n## ", 1)[0]
    header = next(line for line in table.splitlines() if line.strip().startswith("|"))
    assert "no schema tool" in header.lower(), (
        f"the adapter table has no column for a stack this skill does not target: {header!r}"
    )


def test_no_orm_prescription_in_the_schema_of_record_row(deployment_skill_text: str) -> None:
    """The 'schema of record' row must defer to the project's actual stack.

    A skill that says 'the schema of record is the model file' pushes a project
    whose tool was adopted late into generating from stale models, which is the
    exact failure the skill documents elsewhere.
    """
    table = deployment_skill_text.split("### Adapter table", 1)[1].split("\n## ", 1)[0]
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


def test_documents_public_privilege_isolation(deployment_prose: str) -> None:
    """Every role inherits CONNECT from PUBLIC, so role-level revokes do not isolate.

    This is the single most load-bearing provision step on a shared instance, and
    the non-obvious one: revoking from your own role changes nothing.

    The earlier version of this guard required the word "server-wide" and so
    required the wrong claim. REVOKE is per database and never was server-wide;
    asserting that it was baked the misconception into shared doctrine that other
    projects were told to follow.
    """
    lowered = deployment_prose.lower()
    assert "PUBLIC" in deployment_prose
    assert "inherit" in lowered or "inherits" in lowered
    assert "per database" in lowered, "REVOKE is per database, and that is the trap"
    assert "pg_hba" in lowered, "the mechanism that does enforce it should be named"


def test_recommends_pg_hba_over_revoke_from_public(deployment_prose: str) -> None:
    """The enforcement that works, and the one that only appears to.

    `REVOKE CONNECT ... FROM PUBLIC` is the instinctive move and it is a
    different, smaller thing than the instinct expects. `pg_hba.conf` is evaluated
    before any SQL, applies to every database at once, and is scoped to one role.
    A reader following this skill has to be told which one is load-bearing.
    """
    lowered = deployment_prose.lower()
    assert "host-based" in lowered or "host based" in lowered
    assert "first-match" in lowered or "first match" in lowered
    assert "reload" in lowered, "restarting the server would drop other tenants' connections"
    assert "reject" in lowered, "the deny line should be shown, not described"


def test_warns_against_a_second_migration_role(deployment_skill_text: str) -> None:
    """A DDL role that cannot do DDL is a trap someone will fall into again.

    Without ownership, `GRANT CREATE ON SCHEMA` permits creating new objects and
    nothing else; a test that alters a table the role just created appears to
    prove otherwise. The skill has to warn about the test as well as the design,
    because the test is what makes people reinstate the role.
    """
    lowered = deployment_skill_text.lower()
    assert "migration" in lowered
    for phrase in ("ownership", "create"):
        assert phrase in lowered
    assert "just created" in lowered or "just created it" in lowered, (
        "the flattering test should be named, since it is what people rely on"
    )


def test_documents_the_sequence_grant_trap(deployment_prose: str) -> None:
    """A DML role without a sequence grant fails late, on every serial insert.

    Omitting it looks fine until the first write, and the error does not mention
    provisioning.
    """
    lowered = deployment_prose.lower()
    assert "sequence" in lowered
    assert "nextval" in lowered, "the concrete failure mode should be named"


def test_documents_the_deferrable_trap(deployment_prose: str) -> None:
    """The obvious fix for a self-referencing load silently mutates the schema.

    Someone will reach for it, and it will work, which is what makes it dangerous.
    """
    lowered = deployment_prose.lower()
    assert "deferrable" in lowered
    assert "staging" in lowered, "the safe alternative should be named alongside the trap"


def test_seed_is_demoted_from_a_deployment_step(deployment_prose: str) -> None:
    """No deploy should run a seeder.

    Stating the seeder is not a deployment step is what keeps it out of a compose
    file, which is where it otherwise ends up.
    """
    assert "not a deployment step" in deployment_prose.lower()
    assert "allowlist" in deployment_prose.lower(), "the filename-to-table boundary should be named"


def test_provisioning_verification_is_asserted_not_assumed(deployment_skill_text: str) -> None:
    """Capability checks, not a catalog listing.

    Listing databases proves nothing, because every role can see the catalog. The
    concrete privilege attributes belong in a runnable example, so this scans the
    whole document rather than the prose.
    """
    lowered = deployment_skill_text.lower()
    assert "verify the boundary" in lowered or "assert the" in lowered
    for attribute in ("rolsuper", "rolcreatedb", "rolcreaterole"):
        assert attribute in lowered, f"the privilege attribute {attribute} should be named"
    assert "tableowner" in lowered, "the ownership check should be shown, not just described"
