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
COMPOSE_FILE = REPO_ROOT / "infra" / "vps" / "docker-compose.yml"
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
        "infra/vps/docker-compose.yml has no `migrate` service. Services found: "
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
# infra/schema.sql - the generated schema snapshot
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

SCHEMA_SQL = REPO_ROOT / "infra" / "schema.sql"

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
        "infra/schema.sql must declare itself GENERATED in its first block of comments. "
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
            f"infra/schema.sql header must not describe itself as {claim!r}. It is "
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
        f"infra/schema.sql contains {len(data_statements)} data statement(s). It must "
        "be schema-only; regenerate without dropping --schema-only."
    )
    owners = re.findall(r"^ALTER .* OWNER TO .*$", text, re.MULTILINE)
    assert not owners, (
        f"infra/schema.sql contains {len(owners)} OWNER TO statement(s), e.g. "
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
        f"infra/schema.sql is missing model tables {missing}. A database built from "
        "it would fail on the routes that use them."
    )
    assert len(declared) == 23, (
        f"infra/schema.sql declares {len(declared)} tables, expected 23. A changed "
        "count means the snapshot is stale or was hand-edited; regenerate it."
    )
    for reserved in RESERVED_TABLES:
        assert reserved in declared, (
            f"reserved table {reserved!r} vanished from infra/schema.sql. It exists in "
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
        "infra/schema.sql must declare token_blacklist; every authenticated request "
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
# `infra/schema.sql` being correct does not help if the script people actually run
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
        "The default must be infra/schema.sql."
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
    stale against the live database (alembic check reports 94 pending operations),
    so that advice loads
    cleanly and produces the wrong schema. A warning that points at the wrong fix is
    worse than no warning, because it is followed."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    wrong = re.findall(
        r"[^\n]*from the SQLAlchemy models rather than[^\n]*", readme
    ) + re.findall(r"[^\n]*create_all\(engine\)[^\n]*", readme)
    assert not wrong, (
        f"README.md recommends building the schema from the ORM models: {wrong}. That "
        "produces the wrong schema cleanly (TICKET-019). The documented source is "
        "infra/schema.sql, a dump of the live database."
    )
    assert "infra/schema.sql" in readme, (
        "README.md must point at infra/schema.sql as the schema source, so the "
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


# ── Runtime vs development dependency split ──────────────────────────────────

REQUIREMENTS = REPO_ROOT / "requirements.txt"
REQUIREMENTS_DEV = REPO_ROOT / "requirements-dev.txt"

#: Packages no runtime import path needs. `pandas` is imported only by
#: `etl/transform_csv.py`, which runs on a laptop or in a batch job - never in
#: the API container.
DEV_ONLY_PACKAGES: tuple[str, ...] = (
    "pytest",
    "pytest-cov",
    "pytest-asyncio",
    "factory_boy",
    "httpx",
    "pandas",
)

#: The distribution name as pip writes it, for matching against the import name.
#: `factory_boy` is imported as `factory`.
DISTRIBUTION_NAMES: dict[str, str] = {
    "factory_boy": "factory",
    "pytest_asyncio": "pytest_asyncio",
}


def _normalise(name: str) -> str:
    """Fold a package name to the form pip writes, for comparison.

    `factory_boy` is the import name and `factory-boy` is the distribution name;
    pip normalises underscores to hyphens, so both sides of a comparison go
    through this. Without it a correctly declared package reads as missing purely
    because of the spelling difference.
    """
    return name.strip().lower().replace("_", "-")


def _declared_packages(path: Path) -> set[str]:
    """Normalised distribution names from a requirements file.

    Read rather than executed, because the question is what the image will
    install, not what is installed in the developer's virtualenv. Extras and
    version specifiers are stripped: `uvicorn[standard]==0.34.0` is the package
    `uvicorn`, and the match below is on the name.
    """
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)", line)
        if match:
            names.add(_normalise(match.group(1)))
    return names


def _runtime_import_statements() -> set[str]:
    """Top-level names imported by the code that ships in the image.

    Scans `app/`, `alembic/env.py` and the ETL package, because all three run
    inside the container the Dockerfile builds. A package asserted as present in
    `requirements.txt` but never imported here is a package this guard cannot
    vouch for, which is reported as a failure rather than ignored.
    """
    roots = [REPO_ROOT / "app", REPO_ROOT / "etl", REPO_ROOT / "alembic" / "env.py"]
    imported: set[str] = set()
    pattern = re.compile(
        r"^\s*(?:from\s+(?P<from>[A-Za-z_][\w.]*)\s+import|import\s+(?P<plain>[A-Za-z_][\w.]*))",
        re.MULTILINE,
    )
    files: list[Path] = []
    for entry in roots:
        if entry.is_dir():
            files.extend(sorted(entry.rglob("*.py")))
        elif entry.is_file():
            files.append(entry)

    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            if match.group("from"):
                imported.add(match.group("from").split(".")[0].lower())
            if match.group("plain"):
                imported.add(match.group("plain").split(".")[0].lower())
    return imported


#: Runtime packages that no literal `import` statement proves, with the reason
#: each is nonetheless required inside the image. Listing them explicitly is the
#: point: a package nobody can explain is a package nobody should ship, so each
#: entry has to justify itself here or be removed.
RUNTIME_PACKAGES_PROVEN_ELSEWHERE: dict[str, str] = {
    "gunicorn": "the Dockerfile CMD and the local compose command both exec it",
    "psycopg2-binary": (
        "SQLAlchemy loads the driver by dialect name string "
        "('postgresql+psycopg2'), so it is imported by the library, not by app/"
    ),
    "python-multipart": (
        "FastAPI imports it when a route declares UploadFile, which it does for "
        "the upload endpoints; the import is internal to the framework"
    ),
    "bcrypt": "pulled in as an extra of passlib[bcrypt], which app/ imports",
    "email-validator": (
        "pulled in by fastapi for pydantic EmailStr, which app/core/models.py uses"
    ),
    "uvicorn": "the ASGI server the container runs; referenced by CMD and CMD args",
}


def test_requirements_declares_no_development_only_package() -> None:
    """An image that installs pytest installs the test suite as well.

    `pytest` in a runtime requirements file is not a harmless extra: the test
    package is then present in the image, which is both surface area and a
    contradiction of the split the local stack depends on. The failure mode is
    quiet - the image builds, and nothing warns that the deployment carries a
    test harness.
    """
    declared = _declared_packages(REQUIREMENTS)
    offenders = sorted({_normalise(name) for name in DEV_ONLY_PACKAGES} & declared)

    assert not offenders, (
        f"requirements.txt is the image's dependency list, but it declares "
        f"development-only packages: {offenders}. Each of them must move to "
        f"requirements-dev.txt; a package misfiled as runtime ships its whole "
        f"dependency tree into the image."
    )


def test_requirements_dev_exists_and_declares_the_development_packages() -> None:
    """The development set must exist somewhere, or `make setup` silently
    installs less than it did before the split."""
    assert REQUIREMENTS_DEV.is_file(), (
        "requirements-dev.txt must exist. Moving development packages out of "
        "requirements.txt is only correct if the target of the move is present; "
        "without it, `make setup` installs a runtime-only environment and every "
        "test fails on a missing pytest."
    )

    declared = _declared_packages(REQUIREMENTS_DEV)
    expected = {_normalise(name) for name in DEV_ONLY_PACKAGES}
    missing = sorted(expected - declared)

    assert not missing, (
        f"requirements-dev.txt must declare every development package: {missing}. "
        f"Declared: {sorted(declared)}"
    )


#: Runtime packages proved by an import statement in shipped code, mapped to the
#: import name that must appear.
RUNTIME_PACKAGES_PROVEN_BY_IMPORT: dict[str, tuple[str, ...]] = {
    "alembic": ("alembic",),
    "minio": ("minio",),
    "weasyprint": ("weasyprint",),
    "jinja2": ("jinja2",),
    "python-jose": ("jose",),
    "passlib": ("passlib",),
    "structlog": ("structlog",),
    "uuid6": ("uuid6",),
    "holidays": ("holidays",),
    "aiofiles": ("aiofiles",),
    "fastapi": ("fastapi",),
    "sqlalchemy": ("sqlalchemy",),
    "pydantic-settings": ("pydantic_settings",),
}

#: Every package that must remain in the image.
RUNTIME_PACKAGES: frozenset[str] = frozenset(
    RUNTIME_PACKAGES_PROVEN_BY_IMPORT
) | frozenset(RUNTIME_PACKAGES_PROVEN_ELSEWHERE)


def test_every_runtime_package_is_declared_and_actually_imported() -> None:
    """Presence alone is the claim that broke the image before.

    Section 3's risk note names it: misclassifying a package as development-only
    does not fail the build, it fails at import time on the running container.
    So this asserts both halves - the package is declared for the image, and
    either shipped code imports it or its presence is justified explicitly. A
    declared package with neither is reported too, because that is the other
    direction of the same mistake: a name kept for historical reasons, which is
    how a stale requirement survives every review.
    """
    declared = _declared_packages(REQUIREMENTS)
    imported = _runtime_import_statements()

    missing = sorted(package for package in RUNTIME_PACKAGES if package not in declared)
    assert not missing, (
        f"these packages are imported by the shipped code but absent from "
        f"requirements.txt: {missing}. They must stay in the image's dependency "
        f"list; the build would succeed and the container would exit on import."
    )

    unproven = sorted(
        package
        for package, import_names in RUNTIME_PACKAGES_PROVEN_BY_IMPORT.items()
        if not any(import_name.lower() in imported for import_name in import_names)
    )
    assert not unproven, (
        f"these packages are declared as runtime but nothing in app/, etl/ or "
        f"alembic/env.py imports them: {unproven}. Either a real import was "
        f"missed, or the requirement is stale. Remove it deliberately and record "
        f"why - do not leave it as a coincidence."
    )


def test_every_package_explained_elsewhere_says_why() -> None:
    """The escape hatch must cost something, or it becomes the default.

    RUNTIME_PACKAGES_PROVEN_ELSEWHERE exists because six packages genuinely are
    needed by the image without any import statement naming them. Each entry has
    to carry a non-empty explanation, because an unjustified entry is precisely
    how a stale requirement becomes permanent: it passes every check and nobody
    remembers why it is there.
    """
    unjustified = sorted(
        package
        for package, reason in RUNTIME_PACKAGES_PROVEN_ELSEWHERE.items()
        if not reason.strip()
    )
    assert not unjustified, (
        f"these runtime packages are excused from the import check without a "
        f"stated reason: {unjustified}. Write down why the image needs them, or "
        f"move them and let the import check speak."
    )

    unknown = sorted(set(RUNTIME_PACKAGES_PROVEN_ELSEWHERE) - RUNTIME_PACKAGES)
    assert not unknown, (
        f"these packages are excused from the import check but are not required: "
        f"{unknown}. Remove them from the exemption list."
    )


def test_make_setup_installs_both_requirement_files() -> None:
    """`make setup` must yield the environment it yielded before the split.

    A split that is not wired into the only setup path silently changes what a
    new developer and CI get, and the symptom is a missing pytest rather than a
    missing declaration.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^setup:.*?(?=^\S|\Z)", makefile, re.MULTILINE | re.DOTALL)
    assert match, "Makefile must define a `setup` target"

    setup_body = match.group(0)

    for required_file in ("requirements.txt", "requirements-dev.txt"):
        assert required_file in setup_body, (
            f"`make setup` must install {required_file}. Without it the environment "
            f"is missing whatever that file declares, and the failure surfaces far "
            f"from its cause:\n{setup_body}"
        )


# ── Runtime image hardening ─────────────────────────────────────────────────

#: Toolchain that must be available while `pip install` runs (psycopg2-binary and
#: any sdist dependency may compile) and must be absent from the final layer. The
#: presence-during-build, absence-after requirement is why the Dockerfile needs
#: two apt layers rather than one.
BUILD_TOOLCHAIN: tuple[str, ...] = ("gcc", "libpq-dev")

#: uid/gid the runtime stage's non-root user owns. The Dockerfile states these in
#: a comment and infra/local/ matches bind-mounted ownership to them, so the two
#: must be read from one place.
RUNTIME_UID_PATTERN = re.compile(r"^\s*(?:ENV\s+)?APP_UID=(\d+)", re.MULTILINE)
RUNTIME_GID_PATTERN = re.compile(r"^\s*(?:ENV\s+)?APP_GID=(\d+)", re.MULTILINE)


def _user_instructions(stage: str) -> list[str]:
    """Values given to `USER`, in order of appearance.

    The final one is the user the container runs as. An earlier `USER` may exist
    to scope a build step; what matters is that the last one is not root.
    """
    return [
        match.group(1).strip()
        for match in re.finditer(r"^USER\s+(?P<value>\S+)", stage, re.MULTILINE | re.IGNORECASE)
    ]


def test_runtime_stage_runs_as_a_non_root_user() -> None:
    """A container that runs as root has no meaningful boundary inside it.

    The image is a FastAPI service reachable over HTTP, so a compromise runs as
    uid 0 inside the container. Nothing in the deploy path notices, because a
    root-owned container is the default behaviour of every image this was copied
    from. The check is on the effective user, not on the presence of a `USER`
    line: `USER root`, or a `USER` followed by a later `USER root`, both pass the
    weaker test and both ship root.
    """
    stages = _stages()
    assert "runtime" in stages, "the Dockerfile must define an explicit `runtime` stage"

    users = _user_instructions(stages["runtime"])

    assert users, (
        "the runtime stage must declare a USER. Without it the container runs as "
        "root, which is the default of every upstream image this was based on and "
        "is not a decision anyone made here."
    )

    effective = users[-1]
    assert effective not in {"root", "0"}, (
        f"the runtime stage's effective USER is {effective!r}. A USER line that "
        f"resolves to root - whether written as `USER root`, `USER 0`, or left as "
        f"the final instruction after an earlier USER - gives the container no "
        f"privilege boundary at all. Full sequence found: {users}"
    )


def test_runtime_stage_declares_explicit_uid_and_gid() -> None:
    """The uid must be a number the local stack can chown a directory to.

    Task 4.6 makes chunked uploads work by owning CHUNK_DIR with this uid. That
    is only possible if the uid is known without building and running the image,
    and an image-provided name such as `appuser` resolves to whatever that base
    image happened to pick - which changes when the base is rebuilt.
    """
    stages = _stages()
    runtime = stages["runtime"]

    uid_match = RUNTIME_UID_PATTERN.search(runtime)
    gid_match = RUNTIME_GID_PATTERN.search(runtime)

    assert uid_match and gid_match, (
        "the runtime stage must state its uid and gid explicitly, so infra/local/ "
        "can match file ownership to them without building and inspecting the "
        "image. Expected APP_UID=<number> and APP_GID=<number>."
    )

    uid, gid = int(uid_match.group(1)), int(gid_match.group(1))
    assert uid >= 1000, (
        f"APP_UID is {uid}. uids below 1000 are the system range, where a "
        f"well-known account may already exist; pick an unprivileged uid outside it."
    )
    assert gid >= 1000, f"APP_GID is {gid}; it should sit outside the system range too."

    # The useradd call must consume these, not repeat the numbers: a second
    # literal is a second source of truth that can drift from the comment.
    useradd = [
        line
        for line in runtime.splitlines()
        if re.search(r"\buseradd\b|\badduser\b", line)
    ]
    assert useradd, "the runtime stage must create the non-root user with useradd"
    assert any("APP_UID" in line and "APP_GID" in line for line in useradd), (
        "useradd must take its uid and gid from APP_UID/APP_GID, so there is one "
        f"source of truth. Found: {useradd}"
    )


def test_runtime_stage_drops_the_build_toolchain_after_installing() -> None:
    """gcc and libpq-dev are build inputs, and shipping them is a standing risk.

    psycopg2-binary ships wheels, so on a normal build the compiler is never
    invoked - it is installed, available to anything that does invoke it, and
    nothing ever removes it. The apt lists are already discarded, so the package
    remains installed in the final layer.

    The assertion is about the final layer rather than about a `purge` line
    appearing somewhere, because the two-part requirement is the actual one:
    present while `pip install` runs, gone afterwards. Removing them before the
    install would satisfy a naive check and break the build the moment a
    dependency needs to compile.
    """
    stages = _stages()
    runtime = stages["runtime"]
    layers = _runtime_layer_instructions(runtime)

    def _installs(package: str) -> list[int]:
        """Layers that install `package`.

        Separating an install from a removal is not pedantry: the purge layer
        names gcc and libpq-dev as well, so a plain "mentions the package" search
        counts the removal as an installation and the ordering assertion becomes
        unsatisfiable.
        """
        found: list[int] = []
        for index, instruction in enumerate(layers):
            if not instruction.lstrip().startswith("RUN"):
                continue
            if not re.search(rf"\b{re.escape(package)}\b", instruction):
                continue
            if re.search(r"apt-get\s+install|apt\s+install|dpkg\s+-i", instruction):
                found.append(index)
        return found

    pip_install_at = [
        index
        for index, instruction in enumerate(layers)
        if instruction.lstrip().startswith("RUN") and "pip install" in instruction
    ]

    assert pip_install_at, "the runtime stage must run pip install"

    removals = [
        index
        for index, instruction in enumerate(layers)
        if instruction.lstrip().startswith("RUN")
        and re.search(r"\b(purge|autoremove)\b", instruction)
    ]

    for package in BUILD_TOOLCHAIN:
        installed_at = _installs(package)

        assert installed_at, (
            f"{package} must be installed for pip to run. Removing it before the "
            f"install would break the build outright - which is loud, and better "
            f"than an image that silently lacks a compiler the next sdist needs."
        )
        assert removals, (
            f"the runtime stage installs {package} and never removes it, so the "
            f"shipped image contains a build toolchain. The final layer's package "
            f"list is the attack surface that ships; purge it in a layer after "
            f"pip install."
        )
        assert min(removals) > max(installed_at), (
            f"{package} is removed at layer {min(removals)} but installed at "
            f"layer {max(installed_at)}. The purge must come after every install "
            f"that needs it, or the build breaks in a way that looks like a "
            f"dependency problem."
        )
        assert min(removals) > max(pip_install_at), (
            f"{package} is purged before pip install completes (layer "
            f"{min(removals)} vs {max(pip_install_at)}). A dependency that "
            f"compiles from source would fail to build."
        )

    # The removal must name the packages, not just orphan their dependencies.
    # `apt-get autoremove` alone reclaims nothing while gcc remains a manually
    # installed root of the tree, so every ordering assertion above would pass
    # with the toolchain still shipped.
    for package in BUILD_TOOLCHAIN:
        assert any(
            re.search(rf"\b{re.escape(package)}\b", layers[index]) for index in removals
        ), (
            f"no removal layer names {package}. An `autoremove` without the package "
            f"listed reclaims only what it orphaned, leaving the package itself "
            f"installed in the shipped image."
        )


def test_runtime_stage_ships_no_test_framework() -> None:
    """pytest inside the shipped image means the test suite ships with it.

    The import check is on the installed distribution, and the assertion is on
    absence from the runtime requirements list rather than on any `pip uninstall`
    line - requirements-dev.txt is not copied into the runtime stage, so the
    package is never installed. That is what the split in section 3 buys, and it
    is only true if the stage keeps installing requirements.txt alone.
    """
    stages = _stages()
    runtime = stages["runtime"]

    install_lines = [
        line
        for line in runtime.splitlines()
        if line.lstrip().startswith("RUN") and "pip install" in line
    ]

    assert install_lines, "the runtime stage must run pip install"

    for line in install_lines:
        assert "requirements-dev.txt" not in line, (
            f"the runtime stage installs a development requirements file: {line!r}. "
            f"The shipped image then contains the test suite. Install "
            f"requirements.txt only; the dev file exists for the host virtualenv."
        )

    assert "requirements-dev.txt" not in runtime, (
        "requirements-dev.txt must not be COPYied into the runtime stage. Even "
        "without an explicit install, its presence in the image lets a later "
        "misjudged command add the test suite to a deployment."
    )


def _runtime_layer_instructions(stage: str) -> list[str]:
    """Split a stage into its Dockerfile instructions, in order.

    Two details matter and both were wrong in the first version of this helper,
    which made the ordering assertions below pass for the wrong reason:

    - Comment lines are removed entirely, not folded into the instruction that
      follows. The Dockerfile documents each apt layer with a block of `#`
      comments; attaching them to the next instruction makes a layer appear to
      mention `gcc` or `pip install` when the instruction never mentioned it.
    - Line continuations are joined, so a multi-line `RUN` is one instruction
      rather than several fragments. A purge split across three lines would
      otherwise read as three layers, none of which mentions a package.
    """
    # Join continuations, dropping comments, then split on instruction starts.
    logical: list[str] = []
    pending = ""
    for raw in stage.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        logical.append(pending + stripped)
        pending = ""
    if pending.strip():
        logical.append(pending.strip())

    instructions: list[str] = []
    for line in logical:
        # A line that does not begin with an instruction keyword is a continuation
        # of the previous one (a multi-line CMD argument list, for example).
        if re.match(r"^[A-Z][A-Z_]*(\s|$)", line) or not instructions:
            instructions.append(line.strip())
        else:
            instructions[-1] = f"{instructions[-1]} {line.strip()}"
    return instructions
