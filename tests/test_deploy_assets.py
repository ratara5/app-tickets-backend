"""Structural guards for the deployment assets.

The regression these prevent is silent and expensive: an image that cannot run its
own migrations. `alembic` is in `requirements.txt`, so the package is installed,
but until 2026-09-27 the `Dockerfile` copied only `app/`, so neither `alembic/` nor
`alembic.ini` was in the image. `alembic upgrade head` inside the app container
failed with a missing-config error while the container itself started perfectly and
answered its healthcheck. Nothing in CI noticed.

These tests read the Dockerfile, the compose file and the runbook. No container is
built, no database is required, so they run in CI.
"""
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "deploy" / "vps" / "docker-compose.yml"
RUNBOOK = REPO_ROOT / "docs" / "deployment-guide.md"

STAGE_PATTERN = re.compile(r"^FROM\s+\S+(?:\s+AS\s+(?P<name>\S+))?", re.MULTILINE | re.IGNORECASE)


def _stages() -> dict[str, str]:
    """Map stage name -> its full text. The unnamed final stage is the runtime."""
    matches = list(STAGE_PATTERN.finditer(DOCKERFILE.read_text(encoding="utf-8")))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(DOCKERFILE.read_text())
        name = match.group("name")
        if name is None:
            name = "runtime"
        result[name] = DOCKERFILE.read_text(encoding="utf-8")[match.start() : end]
    return result


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_dockerfile_defines_a_migrate_stage() -> None:
    """The migration job must be built from the same source as the app so that
    "what migrated" and "what runs" can never be different code."""
    stages = _stages()
    assert "migrate" in stages, (
        "the Dockerfile must define a `migrate` stage, so the migration job is built "
        f"from the same source as the runtime image. Stages found: {sorted(stages)}"
    )
    assert "runtime" in stages, (
        "the final image must remain an explicit `runtime` stage; without a named "
        "stage a plain `docker build` yields the migration image as the default."
    )
    assert list(stages)[-1] == "runtime", (
        f"a plain `docker build` targets the LAST stage, which is "
        f"{list(stages)[-1]!r}. It must be `runtime`: deploying the migration image "
        "as the application image would ship a container whose CMD runs alembic."
    )


def _migrate_stage() -> str:
    """Read the migrate stage, failing with an actionable message rather than a
    KeyError when it is absent."""
    stage = _stages().get("migrate")
    assert stage is not None, (
        "the Dockerfile has no `migrate` stage, so no image can run migrations. "
        f"Stages found: {sorted(_stages())}"
    )
    return stage


def _migrate_service() -> dict:
    services = _compose()["services"]
    assert "migrate" in services, (
        "deploy/vps/docker-compose.yml has no `migrate` service. Services found: "
        f"{sorted(services)}"
    )
    return services["migrate"]


def test_migrate_stage_carries_the_migration_scripts() -> None:
    """The defect this exists for: the package was installed, the scripts were not."""
    stage = _migrate_stage()
    assert re.search(r"^COPY\s+alembic/", stage, re.MULTILINE | re.IGNORECASE), (
        "the migrate stage must COPY the alembic/ directory; without the revision "
        "scripts `alembic upgrade head` cannot run even though the package is installed"
    )
    assert re.search(r"^COPY\s+alembic\.ini\b", stage, re.MULTILINE | re.IGNORECASE), (
        "the migrate stage must COPY alembic.ini; env.py reads script_location from it"
    )
    assert re.search(r"^COPY\s+app/", stage, re.MULTILINE | re.IGNORECASE), (
        "the migrate stage must COPY app/, because env.py imports the models and a "
        "migration is meaningless without the schema it targets"
    )


def test_migrate_service_is_declared_and_is_not_supervised() -> None:
    """`restart: unless-stopped` on a migration turns one failure into a restart
    loop that re-hammers a Postgres shared with other tenants."""
    migrate = _migrate_service()
    assert str(migrate.get("restart")) == "no", (
        f"the migrate service must be restart: \"no\" (got {migrate.get('restart')!r}). "
        "A supervised migration re-runs on failure against a shared database."
    )
    assert migrate.get("build", {}).get("target") == "migrate", (
        "the migrate service must build the `migrate` target of the same Dockerfile, "
        "so the job and the app are the same commit"
    )


def test_migrate_service_is_networked_but_publishes_nothing() -> None:
    """It needs to reach postgres-gci on infra-net, exactly like the app, and needs
    no published port: it is a job, not an endpoint."""
    migrate = _migrate_service()
    assert "ports" not in migrate, (
        "the migrate service must publish no ports; a migration has no traffic to "
        "receive and every published port is attack surface on a shared host"
    )
    networks = migrate.get("networks") or []
    assert isinstance(networks, list) and "infra-net" in networks, (
        f"the migrate service must join infra-net to reach postgres-gci (got {networks!r})"
    )


def test_shared_data_plane_is_still_declared_by_nobody() -> None:
    """postgres-gci and minio-acme are shared with other applications. This compose
    file must never declare them, or a `down` here becomes an outage over there."""
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    for shared in ("postgres-gci", "minio-acme"):
        assert not re.search(rf"^\s+{shared}:\s*$", text, re.MULTILINE), (
            f"{shared} is shared infrastructure and must not be declared as a service "
            "in this project's compose file"
        )


def test_every_copied_path_survives_dockerignore() -> None:
    """A path excluded from the build context cannot be COPYed.

    This is the guard for a real failure: `alembic/` and `alembic.ini` were listed
    in `.dockerignore`, so the `migrate` stage could not copy the revision scripts
    even though the Dockerfile asked for them. The package was installed, the
    scripts were absent, and the image started and answered its healthcheck while
    being unable to run a migration. Reading the Dockerfile is not enough — the
    build context is a second source of truth about the same files.
    """
    ignored = {
        line.strip()
        for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    copy_sources: set[str] = set()
    for stage in _stages().values():
        for source in re.findall(r"^COPY\s+(.+)$", stage, re.MULTILINE | re.IGNORECASE):
            for token in source.split():
                if token.startswith("--"):
                    continue
                copy_sources.add(token.rstrip("/"))

    blocked = sorted(
        source
        for source in copy_sources
        if source in ignored or f"{source}/" in ignored or source in {f"{i}/" for i in ignored}
    )
    assert not blocked, (
        f"the Dockerfile COPYs {blocked}, but .dockerignore excludes them, so the "
        "build cannot succeed. Remove the exclusion or stop copying the path."
    )


def test_runbook_documents_the_migration_job() -> None:
    """An infrastructure change nobody can find is not a change."""
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert re.search(r"run\s+--rm\s+migrate", runbook), (
        "docs/deployment-guide.md must document the one-shot invocation "
        "(`docker compose run --rm migrate`); `--rm` with `run` is what makes the "
        "job a job instead of a service"
    )
    assert "run --rm migrate alembic heads" in runbook, (
        "the runbook must show a command that can be executed today to prove the "
        "migration scripts are in the image"
    )


def test_runbook_does_not_document_the_exec_antipattern() -> None:
    """`compose exec api alembic …` needs the app already running, so it migrates
    after the code that needs the new column is serving traffic. It is the pattern
    the sibling project uses; it must not become the documented path here."""
    runbook = RUNBOOK.read_text(encoding="utf-8")
    offending = re.findall(r"docker compose exec \S*api\S* [^\n]*alembic[^\n]*", runbook)
    assert not offending, (
        f"the runbook documents the `compose exec` antipattern: {offending}. Use "
        "`run --rm migrate` so migrations happen before the new code serves traffic."
    )


# ---------------------------------------------------------------------------
# deploy/schema.sql - the generated schema snapshot
# ---------------------------------------------------------------------------
#
# `init.sql` was hand-maintained and drifted in both directions until it could not
# build a working database. Its replacement is derived from the live database by
# `pg_dump --schema-only`, and the same dump is the source for the Alembic baseline
# revision, so the dev bootstrap and the production path cannot disagree.
#
# A generated artifact carries a different failure mode from a hand-maintained one:
# nobody regenerates it. These tests cannot detect real drift, because that needs the
# live database. What they CAN do is keep the contract honest - that the file says
# what it is, carries its provenance, and cannot quietly turn into something else.

SCHEMA_SQL = REPO_ROOT / "deploy" / "schema.sql"

RESERVED_TABLES = ("hollidays", "materials", "preliquidated", "services", "uom")

TOKEN_BLACKLIST_COLUMNS = ("jti uuid NOT NULL", "expires_at timestamp without time zone NOT NULL")


def _schema_sql() -> str:
    assert SCHEMA_SQL.exists(), (
        f"{SCHEMA_SQL} is missing. It is the dev bootstrap and the source for the "
        "Alembic baseline. Regenerate it with the command in its own header."
    )
    return SCHEMA_SQL.read_text(encoding="utf-8")


def _schema_tables() -> set[str]:
    return set(
        re.findall(r"^CREATE TABLE (?:public\.)?(\w+)", _schema_sql(), re.MULTILINE)
    )


def test_schema_sql_declares_itself_generated_with_provenance() -> None:
    """The failure mode of every generated file that omits its header: it gets read
    as hand-maintained, edited by hand, and silently diverges from its source.

    `init.sql` proved the point in the other direction - it was hand-maintained, so
    it was always going to be wrong. A generated file must be labelled, dated, and
    attributed to the source it was derived from.
    """
    text = _schema_sql()
    header = text[: text.find("CREATE EXTENSION") if "CREATE EXTENSION" in text else 2000]
    assert "GENERATED FILE" in header, (
        "deploy/schema.sql must declare itself GENERATED in its first block of comments. "
        "An unlabelled generated file is read as hand-maintained and will be edited."
    )
    assert "DO NOT EDIT BY HAND" in header, "the header must forbid hand-editing explicitly"
    assert re.search(r"Repo sha\s*:\s*[0-9a-f]{40}", header), (
        "the header must record the 40-character repo commit it was generated from, so "
        "staleness is detectable after a later commit changes the models"
    )
    assert "pg_dump" in header, (
        "the header must name the exact pg_dump invocation used, so the file can be "
        "reproduced byte-for-byte instead of re-derived by hand"
    )


def test_schema_sql_does_not_claim_to_be_hand_maintained() -> None:
    """The inverse claim is the one that caused the incident. A file that says it is
    hand-maintained invites edits; the replacement must not inherit the wording."""
    header = _schema_sql()[:2000]
    for claim in ("hand-maintained", "hand maintained", "handwritten", "hand-written"):
        assert claim not in header.lower(), (
            f"deploy/schema.sql header must not describe itself as {claim!r}. It is "
            "generated from the live database; edits belong in a migration."
        )


def test_schema_sql_is_schema_only_and_role_portable() -> None:
    """Two things that make a dump unusable or unsafe, both of which are silent.

    Data: `--schema-only` must stay in the command. A dump that carries rows would
    put production data into a repository, and the dev bootstrap would start with
    real tickets.

    Ownership: without `--no-owner`, pg_dump emits `ALTER TABLE … OWNER TO <role>`
    for whatever role happened to own the live objects. That makes the file fail on
    any server where the role has a different name, which is the normal case.
    """
    text = _schema_sql()
    data_statements = re.findall(r"^(?:COPY|INSERT INTO)\s", text, re.MULTILINE)
    assert not data_statements, (
        f"deploy/schema.sql contains {len(data_statements)} data statement(s). It must "
        "be schema-only; regenerate without dropping --schema-only."
    )
    owners = re.findall(r"^ALTER .* OWNER TO .*$", text, re.MULTILINE)
    assert not owners, (
        f"deploy/schema.sql contains {len(owners)} OWNER TO statement(s), e.g. "
        f"{owners[0]!r}. The dump was made without --no-owner, so it now requires a "
        "role that may not exist on the target server."
    )


def test_schema_sql_covers_every_table_the_models_require() -> None:
    """The measured numbers: 23 tables live, 17 in the models. Every model table must
    exist in the schema, or a database built from it 500s on that route.

    The five extra tables are the reserved ones (TICKET-018), which are recorded
    rather than dropped: they exist in production and are referenced by data.
    """
    from app.models.base import Base
    from app.models.registry import _autodiscover_models

    _autodiscover_models("app.models")

    declared = _schema_tables()
    model_tables = set(Base.metadata.tables)
    missing = sorted(model_tables - declared)
    assert not missing, (
        f"deploy/schema.sql is missing model tables {missing}. A database built from "
        "it would fail on the routes that use them."
    )
    assert len(declared) == 23, (
        f"deploy/schema.sql declares {len(declared)} tables, expected 23. A changed "
        "count means the snapshot is stale or was hand-edited; regenerate it."
    )
    for reserved in RESERVED_TABLES:
        assert reserved in declared, (
            f"reserved table {reserved!r} vanished from deploy/schema.sql. It exists in "
            "the live database, so dropping it from the dump would make dev diverge "
            "from production. See TICKET-018."
        )


def test_schema_sql_contains_token_blacklist_with_the_live_column_types() -> None:
    """TICKET-017: `init.sql` omitted the table every authenticated request queries,
    so a database built from it failed open on a missing table.

    The model declares `jti` as `String(36)`. The live database is `uuid`. Copying
    the model here would reproduce the drift, so the test asserts the live types -
    which is the whole reason this file is dumped rather than generated.
    """
    declared = _schema_tables()
    assert "token_blacklist" in declared, (
        "deploy/schema.sql must declare token_blacklist; every authenticated request "
        "queries it (TICKET-017)"
    )
    body = re.search(
        r"CREATE TABLE (?:public\.)?token_blacklist \((.*?)\n\);", _schema_sql(), re.DOTALL
    )
    assert body, "token_blacklist is listed but its CREATE TABLE body was not found"
    for column in TOKEN_BLACKLIST_COLUMNS:
        assert column in body.group(1), (
            f"token_blacklist must declare `{column}` - the live type, not the model's "
            "`String(36)`/nullable variant. This file is a dump of the real schema; a "
            "divergence here means it was hand-edited."
        )


def test_schema_sql_records_the_custom_image_requirement() -> None:
    """The dump needs `pg_uuidv7`, which stock PostgreSQL does not ship. TICKET-007
    is exactly this failure: a load on a standard server that stops early and reports
    success. A file whose header does not say so will be reused on the wrong image."""
    text = _schema_sql()
    assert re.search(r"^CREATE EXTENSION IF NOT EXISTS pg_uuidv7\b", text, re.MULTILINE), (
        "the schema uses uuid_generate_v7() defaults, so the dump must carry a real "
        "`CREATE EXTENSION IF NOT EXISTS pg_uuidv7` statement. Matching the name as a "
        "substring is not enough: it also occurs in this file's own header, so the "
        "guard would pass after the statement was removed and the load would break on "
        "a stock server."
    )
    assert "infrastructure-companies-postgres-gci" in text[:2000], (
        "the header must name the image that provides pg_uuidv7, so nobody loads this "
        "into stock postgres:16 and gets a partially-created schema (TICKET-007)"
    )


def test_schema_sql_is_documented_as_a_bootstrap_not_a_production_path() -> None:
    """The file creates tables inside a database that must already exist, and
    production runs `alembic upgrade head`. If the header implies otherwise, the
    documented procedure drifts back to one raw .sql file in production - the
    outcome this whole exercise exists to prevent."""
    header = _schema_sql()[:2000]
    assert re.search(r"alembic upgrade head", header), (
        "the header must name the production path (`alembic upgrade head`) so this "
        "file is not mistaken for it"
    )
    assert re.search(r"must already exist|already exist", header), (
        "the header must state that the database itself must already exist, so the "
        "missing admin step is documented here and not inferred from a failure"
    )


# ---------------------------------------------------------------------------
# bootstrap.sh - the reachable path to the schema
# ---------------------------------------------------------------------------
#
# `deploy/schema.sql` being correct does not help if the script people actually run
# still points somewhere else. These guard the two defects that kept TICKET-007,
# TICKET-008 and TICKET-017 invisible for months: a default pointing at a broken
# file, and a `psql` invocation that cannot report failure.

BOOTSTRAP = REPO_ROOT / "bootstrap.sh"


def _bootstrap() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


def test_bootstrap_does_not_default_to_the_retired_init_sql() -> None:
    """`init.sql` is retired. It was still the default, so the trap stayed armed:
    running `bootstrap.sh` with no arguments applied a file that cannot build a
    working schema and reported success."""
    default = re.search(r"INIT_FILE_ARG:-([^}\s]+)", _bootstrap())
    assert default, "could not find the INIT_FILE_ARG default in bootstrap.sh"
    assert "init.sql" not in default.group(1), (
        f"bootstrap.sh still defaults --init-file to {default.group(1)!r}, which is the "
        "retired file: it declares an impossible foreign key (TICKET-008), needs an "
        "unavailable extension (TICKET-007), and omits token_blacklist (TICKET-017). "
        "The default must be deploy/schema.sql."
    )


def test_bootstrap_schema_load_cannot_report_false_success() -> None:
    """The exact mechanism that hid three tickets: `psql` without
    `-v ON_ERROR_STOP=1` logs the error, continues past it, and exits 0. The script
    then prints success for a schema that was never built.

    Every psql call that loads a file must stop on the first error.
    """
    loading = [
        line
        for line in _bootstrap().splitlines()
        if re.search(r"psql", line) and re.search(r"<\s*\"?\$?\{?INIT_SQL", line)
    ]
    assert loading, (
        "could not find the psql invocation that loads the schema in bootstrap.sh; "
        "this guard must be updated if that call is restructured"
    )
    for line in loading:
        assert "ON_ERROR_STOP=1" in line, (
            f"the schema load in bootstrap.sh lacks -v ON_ERROR_STOP=1: {line.strip()!r}. "
            "Without it psql exits 0 after an error and the script reports success on "
            "an incomplete schema."
        )


def test_readme_does_not_recommend_generating_the_schema_from_the_models() -> None:
    """The subtle failure: the README correctly forbade `init.sql` and then
    recommended building the schema "from the SQLAlchemy models". The models are
    stale against the live database in 9 measured places, so that advice loads
    cleanly and produces the wrong schema. A warning that points at the wrong fix is
    worse than no warning, because it is followed."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    wrong = re.findall(
        r"[^\n]*from the SQLAlchemy models rather than[^\n]*", readme
    ) + re.findall(r"[^\n]*create_all\(engine\)[^\n]*", readme)
    assert not wrong, (
        f"README.md recommends building the schema from the ORM models: {wrong}. That "
        "produces the wrong schema cleanly (TICKET-019). The documented source is "
        "deploy/schema.sql, a dump of the live database."
    )
    assert "deploy/schema.sql" in readme, (
        "README.md must point at deploy/schema.sql as the schema source, so the "
        "documented procedure and the file bootstrap.sh actually loads are the same"
    )


def test_bootstrap_verifies_the_load_instead_of_asserting_it() -> None:
    """Exit status is necessary but not sufficient: it proves the script ran, not
    that it built the right schema. One cheap post-condition, checked against the
    database, turns 'loaded' into 'loaded and contains the table every request
    needs'."""
    text = _bootstrap()
    assert re.search(r"token_blacklist", text) and "information_schema" in text, (
        "bootstrap.sh must verify after the load that token_blacklist exists, by "
        "querying the database. Without a post-condition, a schema that loads but is "
        "missing the table every authenticated request queries is reported as success "
        "(TICKET-017)."
    )
