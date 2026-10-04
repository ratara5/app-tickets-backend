"""Guards for the local stack, and for the blast radius this change promised to keep.

Two different jobs, one file, because they fail the same way and the reviewer needs
to see them together.

**The blast radius.** This change adds a local stack that consumes shared
infrastructure another project owns. The realistic failure is not a bad YAML file;
it is a well-meaning edit to an asset this repository does not own - a VPS compose
file, a deployment runbook, or the forked copy of the core's own declaration under
`core/`. Such an edit is invisible to every other test here and expensive to undo
from a review, so the six no-touch files are compared byte-for-byte against the
commit recorded in task 1.1.

**The consumer's own rules.** A consumer of shared infrastructure that names
another project's objects, borrows its credentials, hardcodes its directory, or
declares its own copy of a shared dependency is no longer a consumer. Those
failures are cheap to check statically and expensive to discover in production, so
they are checked statically.

Reading files is the whole mechanism: no container is built, no database is
required, so these run in the unit tier.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# The no-touch set
# ---------------------------------------------------------------------------

#: Recorded in task 1.1, before any edit: `git rev-parse HEAD` on `main`.
BASELINE_COMMIT = "e830c24f334c05d428bb82b30be51b8a70adfcd4"

#: The six files this change must not touch, and why each one is here.
#:
#: `core/compose.yml` is last on purpose. It is a fork of a declaration that is
#: still live in the project that owns the shared core, and it has already drifted
#: from that counterpart. Its drift is a real defect, and fixing it here is exactly
#: the wrong move: it is a file this repository does not own, and the fix belongs to
#: the project whose declaration the running container was created from.
NO_TOUCH_FILES: dict[str, str] = {
    "infra/vps/docker-compose.yml": "the VPS deploy contract; this change only consumes it",
    "infra/vps/Caddyfile": "the VPS TLS edge; the local stack declares no TLS edge",
    # `docs/deployment-guide.md` was here for the local-stack change. The harness
    # migration is the separate change this guard anticipated: it updated the
    # document's `deploying-backend-vps` reference from the removed `ai-specs/` tree
    # to the projected `.opencode/skills/` path. Removed from the set rather than
    # re-baselined, so the other five stay protected.
    "infra/schema.sql": "a pg_dump of the live database; generated, so an edit is silently discarded",
    "infra/provision/001-create-application-roles.sql": (
        "the least-privilege role definition, reused locally with substituted "
        "placeholders rather than forked"
    ),
    "core/compose.yml": (
        "a fork of another project's live declaration; the drift in it is a finding "
        "for that project, not an edit for this one"
    ),
}

ROOT_COMPOSE = REPO_ROOT / "docker-compose.yml"
LOCAL_DIR = REPO_ROOT / "infra" / "local"
LOCAL_COMPOSE = LOCAL_DIR / "docker-compose.yml"
MAKEFILE = REPO_ROOT / "Makefile"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _local_asset(relative: str) -> Path:
    """Resolve a file this change is expected to create, with an actionable failure.

    Without this the assertion below would report a `FileNotFoundError` from
    `read_text`, which reads as a bug in the test rather than as a missing asset.
    """
    path = REPO_ROOT / relative
    assert path.exists(), (
        f"{relative} is missing. It is part of the local stack this change adds, so "
        "its absence is a real gap, not a test artefact. Assets expected under "
        f"{LOCAL_DIR.relative_to(REPO_ROOT)}/ : see the 'Local stack definition' "
        "section of openspec/changes/local-stack/tasks.md"
    )
    return path


def _local_scope_files() -> list[Path]:
    """Every file this change owns for local operation, and only those.

    The scope is deliberate. A repository-wide scan for a foreign project's path
    would also match `bootstrap.sh` and the change's own planning documents, which
    legitimately *record* the out-of-tree location rather than depending on it. What
    must never appear is a live dependency on it, and that lives in the files below.
    """
    files = [MAKEFILE, ENV_EXAMPLE]
    if LOCAL_DIR.is_dir():
        files.extend(sorted(p for p in LOCAL_DIR.rglob("*") if p.is_file()))
    return files


# ---------------------------------------------------------------------------
# The local stack exists
# ---------------------------------------------------------------------------
#
# Asserted first, and deliberately, so that a suite run before the local stack is
# written fails here rather than passing vacuously through the rules below. Every
# other test in this file either reads a committed file that already exists or
# reads `infra/local/`, so without this one the file would report success for a
# local stack that is not there.


@pytest.mark.parametrize(
    "relative",
    [
        "infra/local/docker-compose.yml",
        "infra/local/setup.sh",
        "infra/local/scripts/gate-local.sh",
    ],
)
def test_local_stack_asset_exists(relative: str) -> None:
    _local_asset(relative)


# ---------------------------------------------------------------------------
# 1.2 The no-touch set is byte-identical to the recorded baseline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", sorted(NO_TOUCH_FILES))
def test_no_touch_file_is_byte_identical_to_the_baseline_commit(relative: str) -> None:
    """The guard for the failure this change is most likely to cause by accident.

    An edit to one of these six files would not fail any functional test here. It
    would reach review as a small, plausible-looking diff, and the reviewer's
    attention goes to the local stack that is the point of the change. Comparing
    against the baseline commit rather than a stored copy of the bytes means the
    check cannot itself drift, and the failure names the commit to diff against.
    """
    reason = NO_TOUCH_FILES[relative]
    current = (REPO_ROOT / relative).read_bytes()

    baseline = _git("cat-file", "-p", f"{BASELINE_COMMIT}:{relative}")
    assert baseline.returncode == 0, (
        f"could not read {relative} at {BASELINE_COMMIT}. Is the baseline commit "
        f"reachable from this clone? {baseline.stderr.strip()}"
    )
    baseline_bytes = baseline.stdout.encode("utf-8")

    assert current == baseline_bytes, (
        f"{relative} differs from the baseline commit {BASELINE_COMMIT}. This change "
        f"declared it no-touch because it is {reason}. If the edit is genuinely "
        "required, it belongs in a separate change that states the reason here; it "
        f"does not belong in this one. Inspect with: git diff {BASELINE_COMMIT} -- {relative}"
    )


# ---------------------------------------------------------------------------
# 1.3 The root compose file stays inert, and the local stack never reaches for it
# ---------------------------------------------------------------------------


def test_root_compose_still_declares_no_services() -> None:
    """`docker compose up` at the repository root is a documented no-op.

    The root file's `include` entries are all commented out with an explanation
    that the containers moved to other projects. Reintroducing a service there would
    create a second, competing declaration of infrastructure that is now shared -
    which is the outcome this whole change exists to prevent.
    """
    compose = yaml.safe_load(ROOT_COMPOSE.read_text(encoding="utf-8")) or {}
    services = compose.get("services") or {}
    assert not services, (
        f"the root docker-compose.yml declares {sorted(services)}. The shared "
        "infrastructure this project consumes is declared by the project that owns "
        "it; declaring a second copy here makes name resolution ambiguous and turns "
        "`docker compose down` into an outage for the other consumers."
    )


#: A compose subcommand. A line that both names compose and carries one of these is
#: an invocation; a line that merely mentions the filename — assigning it to a
#: variable, `awk`-ing the network name out of it, or naming it in an error
#: message — is not, and cannot resolve to the root file however it is worded.
_COMPOSE_SUBCOMMAND = re.compile(
    r"\bdocker(?:-compose|\s+compose)\b.*\b"
    r"(up|down|build|run|create|start|stop|restart|ps|exec|port|logs|pull|config"
    r"|rm|kill|pause|unpause|wait|publish|images|version|top|events|scale|attach"
    r"|cp|watch)\b"
)


def test_no_local_path_uses_the_root_compose_file() -> None:
    """Bring-up and teardown must name the local compose file explicitly.

    An unqualified `docker compose` command resolves to the root file, which
    declares no services - so it would silently do nothing and report success.

    Detection requires a compose SUBCOMMAND, not just the word "docker-compose".
    Matching the bare filename flagged `COMPOSE_FILE="${PROJECT_ROOT}/infra/local/
    docker-compose.yml"` and the `awk` that reads the network name out of it — lines
    that cannot invoke anything. A guard that fires on a path reference trains people
    to route around it, so the test asks whether the line is a command.
    """
    offenders: list[str] = []
    for path in _local_scope_files():
        if path.suffix not in {".sh", ".yml", ".yaml", ".mk"} and path != MAKEFILE:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not _COMPOSE_SUBCOMMAND.search(stripped):
                continue
            if "-f" in stripped or "--file" in stripped:
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {stripped}")

    assert not offenders, (
        "these commands invoke docker compose without naming a file, so they resolve "
        f"to the root docker-compose.yml, which declares no services:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# 1.4 No committed file carries a password-shaped literal
# ---------------------------------------------------------------------------

#: Keys whose value is a credential. A committed literal for any of these is a
#: leaked credential whether or not it is the real one, because nobody can tell.
CREDENTIAL_KEYS = (
    "DB_PASSWORD",
    "DB_ADMIN_PASSWORD",
    "MINIO_SECRET_KEY",
    "MINIO_ROOT_PASSWORD",
    "JWT_SECRET",
    "SEED_USER_PASSWORD",
)

#: A value that is obviously an instruction rather than a credential. Anything
#: matching this is documentation, not a secret.
PLACEHOLDER_PATTERN = re.compile(
    r"""^(
        $                                   # empty: the key must be filled locally
      | GENERATE_\w+
      | CHANGE_\w+
      | PASTE_\w+
      | REPLACE_\w+
      | <[^>]+>                            # <generated-password>, <admin-password>
      | (?:\$\(|`)?openssl\s+rand\b.*       # the generation command itself
      | \$\{[A-Z_]+\}                      # a shell/compose expansion, not a literal
    )$""",
    re.VERBOSE | re.IGNORECASE,
)

ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(?:export\s+|ENV\s+)?(?P<key>[A-Z0-9_]+)\s*[:=]\s*(?P<value>.*?)\s*$"
)


def test_no_committed_file_carries_a_credential_literal() -> None:
    """A placeholder is documentation. A value that merely looks like one is a leak.

    The distinction that matters is not "is this the production secret" but "could a
    reader tell". `GENERATE_WITH_OPENSSL_RAND_BASE64_32` is unambiguous; a 44-character
    base64 string under `DB_PASSWORD` is indistinguishable from the real one, and
    the next developer to copy `.env.example` ships it.
    """
    offenders: list[str] = []
    for path in _local_scope_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = ASSIGNMENT_PATTERN.match(stripped)
            if match is None or match.group("key") not in CREDENTIAL_KEYS:
                continue
            value = match.group("value").strip().strip("\"'")
            if PLACEHOLDER_PATTERN.match(value):
                continue
            offenders.append(
                f"{path.relative_to(REPO_ROOT)}:{number}: "
                f"{match.group('key')}={value[:8]}... ({len(value)} chars)"
            )

    assert not offenders, (
        "a credential key carries a literal value in a committed file. Commit the "
        "generation instruction instead, and read the real value from the "
        "git-ignored .env:\n" + "\n".join(offenders)
    )


def test_the_env_example_names_every_required_credential_key() -> None:
    """The guard above is only useful if the template still tells the developer what
    to fill in. A key removed from `.env.example` stops being scanned and starts
    being unset, and settings.py now aborts on a missing required key."""
    present = {
        match.group("key")
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if (match := ASSIGNMENT_PATTERN.match(line.strip()))
    }
    for key in ("DB_PASSWORD", "MINIO_SECRET_KEY", "JWT_SECRET"):
        assert key in present, (
            f".env.example no longer carries {key}. Settings declares it required, so "
            "a developer copying the template gets a process that aborts at import."
        )


# ---------------------------------------------------------------------------
# 1.5 No foreign project name, credential, or absolute path
# ---------------------------------------------------------------------------

#: Compose projects and containers observed on this host that belong to other
#: projects. Naming them here is what lets the assertion below be specific; none of
#: them is a value the local stack could legitimately be configured with, because
#: the local stack declares no database and no object store at all.
FOREIGN_OWNERS: tuple[str, ...] = (
    "airflow",
    "bq-api-tecfrio",
    "dopamine",
    "gm-api-tecfrio",
    "gm-scheduler-tecfrio",
    "machado-pg",
    "provider-backend",
    "provider-frontend",
    "scraping_service_v2",
)

#: Directories belonging to another project on this machine. The shared core is
#: genuinely reached through one of them, which is why the location is a configured
#: input rather than a constant (see the `*_COMPOSE_COMMAND` key in .env.example).
FOREIGN_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/home/[A-Za-z0-9._-]+/Documents/"),
    re.compile(r"~/Documents/GoogleCloudProjects"),
    re.compile(r"Documents/GoogleCloudProjects"),
)


def test_no_local_file_names_another_projects_objects() -> None:
    """Isolation is expressed by name: your database, your role, your bucket.

    A file that named another tenant's database or bucket would not fail here or in
    any other test - it would fail when a query landed in someone else's data. The
    shared core hosts several applications, so the name is the only boundary.
    """
    offenders: list[str] = []
    for path in _local_scope_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for owner in FOREIGN_OWNERS:
                if owner in lowered:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{number}: names {owner!r}"
                    )
    assert not offenders, (
        "a local file names an object belonging to another project on the shared "
        "core. Isolation is by name - this project's own database, role, bucket and "
        "credentials - and a name from another project in a local file is either a "
        "mistake or a cross-tenant reference:\n" + "\n".join(offenders)
    )


def test_no_local_file_hardcodes_an_absolute_path_into_another_project() -> None:
    """The core's location is a configured input, not a constant.

    `make setup-local` asks for the core through a key in `.env`, because the core
    lives in a repository this project does not own. Encoding its path here would
    make this repository fail the moment that other repository is moved, and would
    make the dependency invisible: an absolute path reads as a local decision.
    """
    offenders: list[str] = []
    for path in _local_scope_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern in FOREIGN_PATH_PATTERNS:
                if pattern.search(stripped):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{number}: {stripped[:100]}"
                    )
    assert not offenders, (
        "a local file hardcodes a path into another project's directory. The shared "
        "core is reached through the configured key in .env, owned and maintained by "
        "the project that operates it:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# 5. The local stack definition: consumers, not providers
# ---------------------------------------------------------------------------

VPS_COMPOSE = REPO_ROOT / "infra" / "vps" / "docker-compose.yml"

#: Service names that belong to the core. None of them may appear as a service in
#: the local file: declaring one would create a second instance that shares
#: nothing with the real dependency.
CORE_SERVICE_NAMES: tuple[str, ...] = (
    "postgres-gci",
    "minio-acme",
    "pgadmin-gci",
    "caddy",
    "caddy-acme",
)

#: Names whose presence would mean this stack owns a dependency's storage.
DEPENDENCY_IMAGE_HINTS: tuple[str, ...] = (
    "postgres",
    "minio",
    "bitnami",
    "pgadmin",
)


def _volume_source(entry: str) -> str:
    """The host-side source of a compose volume entry.

    Handles both syntaxes compose accepts. Short syntax is `source:target[:mode]`,
    so the colon is not a reliable separator — a named volume has one too. Long
    syntax is a mapping with a `source` key. On Windows a drive letter would
    introduce a colon of its own, which is why the target is only split on a
    colon that is not part of a one-letter drive prefix.
    """
    if isinstance(entry, dict):
        return str(entry.get("source", entry.get("type", "")))

    text = str(entry)
    if len(text) > 1 and text[1] == ":" and text[0].isalpha():
        # A drive letter: the first colon belongs to the path.
        return text.split(":")[0] + ":" + text.split(":")[1].split(":")[0]
    return text.split(":")[0]


#: Prefixes that make a volume source a location on this machine rather than the
#: name of a volume some other compose project declared.
SHARED_VOLUME_SOURCE_PREFIXES: tuple[str, ...] = ("/", "./", "../", "~/", "$")


def _local_compose() -> dict:
    """The parsed local compose file, with the file's own path for messages."""
    return yaml.safe_load(_local_asset("infra/local/docker-compose.yml").read_text())


def _vps_compose() -> dict:
    return yaml.safe_load(VPS_COMPOSE.read_text())


def _local_services() -> dict:
    return _local_compose().get("services", {}) or {}


def test_local_compose_publishes_only_the_api_on_loopback() -> None:
    """One published port, on loopback, and it is the API's.

    Two distinct mistakes are covered by this shape. Publishing on `0.0.0.0`
    puts an unauthenticated-in-development FastAPI service on the LAN, where
    every colleague's machine can write to the shared core's database. Publishing
    the database or the object store would put the core's storage on the
    developer's LAN as well — and those ports belong to the core's own
    declaration, which already binds them to loopback for exactly this reason.
    """
    services = _local_services()

    published: dict[str, list[str]] = {}
    for name, service in services.items():
        entries = service.get("ports") or []
        if entries:
            published[name] = [str(entry) for entry in entries]

    assert set(published) == {"api"}, (
        f"only the api service may publish a port; found ports on {sorted(published)}. "
        f"Everything else this stack uses belongs to the core, whose own declaration "
        f"already decides how it is exposed."
    )

    for entry in published["api"]:
        assert entry.startswith("127.0.0.1:"), (
            f"the api port must be bound to loopback, not to every interface: {entry!r}. "
            f"'0.0.0.0:8000:8000' publishes a development API on the LAN, where it can "
            f"write to a database shared with other projects."
        )


def test_local_compose_declares_no_core_service() -> None:
    """The local stack consumes the core; it never declares a copy of it.

    A second `postgres-gci` here would satisfy every connectivity check in this
    file while testing nothing about the real dependency. It would also be a
    different database with different data, so a passing local run would say
    nothing about the deployed one — the failure mode this whole change exists to
    remove.
    """
    names = {name.lower() for name in _local_services()}

    offenders = sorted(names & set(CORE_SERVICE_NAMES))
    assert not offenders, (
        f"the local compose file declares {offenders}. These belong to the core; "
        f"declaring them locally creates a second instance that shares nothing with "
        f"the dependency actually in use. The local stack reaches the core's "
        f"containers by name across the core's own networks."
    )


def test_local_compose_declares_no_dependency_image_or_build() -> None:
    """No image or build key may name a database or an object store.

    Checked on the value, not on the key's presence: `api` legitimately has both
    `build:` and `image:`, so the assertion cannot be "there is no image key".
    What it rejects is a key whose value names a datastore, which is the only way
    such a dependency can enter a compose file.
    """
    services = _local_services()

    offenders: list[str] = []
    for name, service in services.items():
        for key in ("image", "build"):
            value = service.get(key)
            if value is None:
                continue
            text = value if isinstance(value, str) else str(value)
            for hint in DEPENDENCY_IMAGE_HINTS:
                if hint in text.lower():
                    offenders.append(f"{name}.{key} = {text!r} (matches {hint!r})")

    assert not offenders, (
        f"the local compose file names a database or object-store image: {offenders}. "
        f"The core provides both; a second instance here would test a database nobody "
        f"deploys."
    )


def test_local_compose_declares_no_volume_and_no_shared_volume_reference() -> None:
    """No volume is declared, and none belongs to another compose project.

    Two directions, and the second is the dangerous one. A *declared* volume would
    mean this stack persisting state it does not own. A *referenced* volume would
    mean mounting the core's storage — `infrastructure-companies_postgres-gci-data`,
    `assync_acme_minio_data` — which is the shared database's files appearing in
    this project's container, writable, under a name the teardown does not own.

    The shared names are named in the failure message only. They are the core's,
    not a value this stack may be configured with, and listing them here is how
    they would quietly end up in a local compose file.
    """
    compose = _local_compose()

    assert "volumes" not in compose, (
        f"the local compose file declares a top-level volumes section: "
        f"{sorted(compose['volumes'])}. There is no local data to protect — the "
        f"database, the bucket and the uploaded objects all belong to the core."
    )

    shared_volumes = (
        "infrastructure-companies_postgres-gci-data",
        "assync_acme_minio_data",
    )

    offenders: list[str] = []
    for name, service in _local_services().items():
        for entry in service.get("volumes") or []:
            text = str(entry)
            for shared in shared_volumes:
                if shared in text:
                    offenders.append(f"{name}.volumes contains {shared!r}")
            if _volume_source(text).startswith(SHARED_VOLUME_SOURCE_PREFIXES):
                continue
            # Anything whose source is not a path is a named volume, and a named
            # volume has to be declared in the top-level section rejected above.
            # Short syntax (`name:/path`) is separated by a colon, so the colon
            # cannot be what distinguishes the two: what distinguishes them is
            # whether the source before it looks like a filesystem location.
            offenders.append(
                f"{name}.volumes entry {text!r} names the volume "
                f"{_volume_source(text)!r} instead of mounting a path"
            )

    assert not offenders, (
        f"the local compose file mounts storage it does not own: {offenders}. "
        f"Volumes the core owns: {list(shared_volumes)}"
    )


def test_exactly_one_project_owned_network_carries_both_dependencies() -> None:
    """One network, ours, with both dependencies reachable across it.

    Both services must attach to it. The alternative — one network per dependency —
    is a topology production does not use: `infra/vps/docker-compose.yml:205-209`
    joins a single network with both dependencies attached, so a two-network local
    stack would rehearse a shape that is never deployed.

    The network is not `external`, because this stack creates it and connects the
    core's containers to it. An external network was the previous decision, reversed
    on 2026-10-01: it avoided touching the core at all, but it encoded another
    repository's network naming as a requirement of this one, and the estate has
    already demonstrated the cost — `my-dopamine-network` currently has no members
    and no owning project, so its attachments are lost on container recreate and
    the network itself is prunable.
    """
    compose = _local_compose()
    networks = compose.get("networks") or {}

    assert len(networks) == 1, (
        f"the local stack declares exactly one network, found {sorted(networks)}. "
        f"One network with both dependencies attached is the shape the deployed "
        f"arrangement uses; two networks would rehearse a topology that never ships."
    )

    for name, definition in networks.items():
        assert isinstance(definition, dict), (
            f"network {name!r} has no definition block, so compose creates it "
            f"implicitly with a name derived from the project name. The bring-up "
            f"command has to name this network to connect the core's containers, so "
            f"the name must be stated."
        )
        assert definition.get("external") is not True, (
            f"network {name!r} is declared external. This stack creates its own "
            f"network and connects the core's containers to it; declaring it external "
            f"means depending on a network whose attachments are lost whenever those "
            f"containers are recreated."
        )
        assert definition.get("name"), (
            f"network {name!r} must carry an explicit `name:`. `make setup-local` "
            f"passes this string to `docker network connect`, so it must not be "
            f"derived from a compose key that can be renamed."
        )

    for service_name, service in _local_services().items():
        attached = service.get("networks") or []
        assert attached == list(networks), (
            f"service {service_name!r} attaches to {attached}, but the single local "
            f"network is {list(networks)}. A service left on the default bridge "
            f"cannot resolve postgres-gci or minio-acme at all."
        )


def test_no_local_file_depends_on_a_network_another_project_owns() -> None:
    """The local stack must not acquire a dependency on someone else's network name.

    Four names are named here, and none of them may appear in a file this change
    owns. Each one is a way for this repository to acquire a failure it cannot fix:

    - `infrastructure-companies_gci-db-network` and `assync_as-sync-acme-network` are
      the sibling mirror's networks. They illustrate two deployable shapes (one
      shared `postgres-apps` server, one MinIO per application), not an arrangement
      this repository must reproduce, and renaming one there breaks every consumer
      here with a DNS error the healthcheck does not catch.
    - `core_gci-db-network` is a stale duplicate of the PostgreSQL network with no
      members. Joining it connects this stack to nothing while appearing to work.
    - `my-dopamine-network` is dopamine's. It is also the only network whose absence
      would be an outage for someone else, so it is never a local dependency. On this
      machine it has no members and no owning compose project, so `docker network prune`
      would remove it.
    - `my-tickets-network` is this app's OWN deployed network under the estate's per-app
      pattern (provider-portal/README.md, Infrastructure §1). It belongs in
      `infra/vps/docker-compose.yml`, which is no-touch here, and it is created on the VPS by
      the deployment procedure. Naming it in a local file would be the same category of error as
      the four above: a local stack reaching for a deployed artefact it does not own and cannot
      create. The local instance of the same pattern is `app-tickets-local-net`, created and
      destroyed by `make setup-local`. Recorded here so the name is refused in code, while the
      reasoning that explains it stays readable in the compose file's comments.
    """
    foreign_networks = (
        "infrastructure-companies_gci-db-network",
        "assync_as-sync-acme-network",
        "core_gci-db-network",
        "my-dopamine-network",
        "my-tickets-network",
    )

    offenders: list[str] = []
    for path in _local_scope_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # The compose file names these in its comment block, to explain why it
            # does not use them. Reading that explanation as a violation would make
            # the file self-censoring and the reasoning unauditable.
            if stripped.startswith("#"):
                continue
            for network in foreign_networks:
                if network in line:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{number} names {network}"
                    )

    assert not offenders, (
        f"local files reference a network owned by another project: {offenders}. "
        f"This stack declares and owns one network of its own; depending on a name "
        f"someone else may rename or prune couples this repository's connectivity to "
        f"another project's housekeeping."
    )


def test_local_services_set_no_container_name() -> None:
    """A fixed container name detaches a container from its compose project label.

    `docker compose down` selects by label, not by name, so a `container_name`
    here does not break teardown — it makes the container untearable by its own
    project while remaining stoppable by anyone matching the name. That is how a
    teardown aimed at this project ends up aimed at another tenant's container.
    """
    offenders = {
        name: service["container_name"]
        for name, service in _local_services().items()
        if "container_name" in service
    }

    assert not offenders, (
        f"these local services pin a container_name: {offenders}. Compose acts by "
        f"project label; a fixed name produces a container this project can create "
        f"but not clean up, and a name borrowed from the core would resolve "
        f"ambiguously across the shared networks."
    )


def test_local_compose_cannot_act_on_a_container_it_does_not_own() -> None:
    """No lifecycle command against a container belonging to someone else.

    The rule is symmetric and that is the point. `bootstrap.sh:79` does
    `docker start postgres-gci`, which couples this repository to the core's
    lifecycle; issuing the mirror image — `docker stop postgres-gci` — is an
    outage for every other project on that database. Both are the same error in
    different directions: treating a shared dependency as ours.
    """
    text = _local_asset("infra/local/docker-compose.yml").read_text()
    # Comments are excluded deliberately: the file explains at length why these
    # commands are absent, and reading that explanation as a violation would make
    # the file self-censoring.
    commands = [
        line.strip()
        for line in text.splitlines()
        if not line.strip().startswith("#")
    ]
    body = "\n".join(commands)

    forbidden = ("docker restart", "docker stop", "docker rm", "docker start")
    found = [command for command in forbidden if command in body]

    assert not found, (
        f"the local compose file contains {found}. Every container the core owns is "
        f"not this repository's to act on: starting one couples us to its lifecycle, "
        f"and stopping one is an outage for another tenant."
    )


def _resolved_dependency_endpoints(compose_path: Path, service_name: str) -> dict[str, str]:
    """The four endpoints a service actually resolves, after `environment:` wins.

    Resolution order matters and is the whole point of the comparison: compose
    applies `env_file` first and `environment:` over it, and the failure this
    guards against is a value in one file silently outranking the other. So the
    overrides are applied here in the same order compose applies them, rather than
    reading one source and hoping it is the effective one.
    """
    compose = yaml.safe_load(compose_path.read_text())
    service = (compose.get("services") or {})[service_name]

    effective: dict[str, str] = {}
    for env_file in service.get("env_file") or []:
        env_path = (compose_path.parent / env_file).resolve()
        if not env_path.is_file():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            effective[key.strip()] = value.split("#")[0].strip()

    for key, value in (service.get("environment") or {}).items():
        effective[str(key)] = str(value)

    keys = ("DB_HOST", "DB_PORT", "MINIO_ENDPOINT", "MINIO_PORT")
    return {key: effective[key] for key in keys if key in effective}


def test_local_and_vps_reach_dependencies_identically() -> None:
    """Parity with the deployed arrangement is the point, so it is asserted.

    A local environment that is nearly right is worse than one that is obviously
    wrong, because the difference only shows up after deployment. This compares
    the internal dial target — the four values that decide where queries and
    uploads actually go — between the local `api` service and the VPS `api`
    service, after `environment:` has outranked `env_file:` in both.

    Only the dial target is compared. The *public* origin deliberately differs:
    production signs MEDIA_DOMAIN over TLS behind Caddy, and locally there is no
    TLS edge and no public name. Comparing those too would assert that local
    signs URLs nothing can fetch.
    """
    local = _resolved_dependency_endpoints(LOCAL_COMPOSE, "api")
    vps = _resolved_dependency_endpoints(VPS_COMPOSE, "api-acme")

    assert set(local) == set(vps) == {
        "DB_HOST",
        "DB_PORT",
        "MINIO_ENDPOINT",
        "MINIO_PORT",
    }, (
        f"both api services must resolve the same four endpoints. "
        f"local={local}, vps={vps}"
    )

    differences = {
        key: (local[key], vps[key])
        for key in local
        if local[key] != vps[key]
    }

    assert not differences, (
        f"the local api service resolves different dependencies than the deployed "
        f"one: {differences}. A local environment is a rehearsal; if it dials "
        f"differently, a passing local run says nothing about the deployment. "
        f"Inside a container 127.0.0.1 is the container, which is why both use the "
        f"core's container names and in-container ports "
        f"(infra/vps/docker-compose.yml:71-80)."
    )


#: The only core-container mutations this repository is permitted. Everything else
#: is a lifecycle operation on a container the core's project owns.
ALLOWED_CORE_MUTATIONS: tuple[str, ...] = (
    "docker network connect",
    "docker network disconnect",
)


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """Non-comment, non-blank lines with their numbers.

    Comments are excluded because the local files explain at length which commands
    are forbidden and why. Reading that explanation as a violation would make the
    files self-censoring, and would remove the only record of the reasoning.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.strip().startswith("#")
    ]


def test_no_local_file_mutates_a_core_container_outside_our_network() -> None:
    """A lifecycle command against a core container is forbidden in both directions.

    `bootstrap.sh:79` does `docker start postgres-gci`, which couples this repository
    to the core's lifecycle. The mirror image — `docker stop postgres-gci` — is an
    outage for every other project on that database. Both are the same mistake:
    treating a shared dependency as ours.

    The single exception is attaching a container to, or detaching it from, the
    network this stack owns. That is the pattern the change adopts, and it is scoped:
    the network named on the line must be ours, or the command is mutating a
    container's membership of a network somebody else depends on.
    """
    our_networks = set()
    for definition in (_local_compose().get("networks") or {}).values():
        if isinstance(definition, dict) and definition.get("name"):
            our_networks.add(str(definition["name"]))
        else:
            our_networks.update(_local_compose().get("networks") or {})

    forbidden = ("docker restart", "docker stop", "docker rm", "docker start")

    offenders: list[str] = []
    for path in _local_scope_files():
        for number, line in _code_lines(path):
            for command in forbidden:
                if command not in line:
                    continue
                # `docker compose ... stop` and `docker compose ... down` act by
                # project label on containers compose created, so they are this
                # project's own business and are not in the forbidden set above.
                if "compose" in line:
                    continue
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{number} contains {command!r}"
                )

    assert not offenders, (
        f"local files contain lifecycle commands against containers this repository "
        f"does not own: {offenders}. Starting one couples us to its lifecycle; "
        f"stopping one is an outage for another tenant. The only permitted mutation "
        f"is {list(ALLOWED_CORE_MUTATIONS)} against {sorted(our_networks)}."
    )


def test_network_membership_changes_name_only_our_own_network() -> None:
    """`docker network connect` must name this stack's network, and nothing else.

    The command is permitted, so the risk is where it points. Connecting a core
    container to a network it did not ask for changes its reachability for every
    other consumer on that network — including, if the network were the core's own,
    for tenants this repository has never heard of. Scoping the assertion to the
    local network's own name keeps the exception from becoming a general licence.
    """
    network_names = {
        str(definition.get("name", key))
        for key, definition in (_local_compose().get("networks") or {}).items()
    }
    assert network_names, "the local compose file must declare exactly one network"

    offenders: list[str] = []
    for path in _local_scope_files():
        for number, line in _code_lines(path):
            if "docker network connect" not in line and "docker network disconnect" not in line:
                continue
            named = any(name in line for name in network_names)
            if not named:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{number} names no local network: "
                    f"{line.strip()[:70]}"
                )

    assert not offenders, (
        f"network membership changes must target this project's own network "
        f"{sorted(network_names)}: {offenders}. Attaching a core container to a "
        f"network it did not choose changes its reachability for every other "
        f"consumer of that network."
    )


def test_core_containers_are_never_started_to_make_the_network_work() -> None:
    """The connect step runs after the container is confirmed running.

    Ordering is the requirement, and it is the reason the local pattern is not a
    trap: `docker network connect` on a stopped container succeeds and produces a
    container that is correctly attached to a network it is not using. Nothing
    reports it, and the first symptom is a dependency the API cannot reach while
    the API itself is healthy.

    The check is structural — the state test must appear in the bring-up script
    before any connect — because a runtime ordering claim in prose is not
    verifiable, and the failure is silent.
    """
    # `_code_lines` takes the path and reads it itself. Handing it the already-read
    # text made every assertion here raise AttributeError before running, which is
    # how this test reported as an infrastructure failure instead of a verdict.
    setup = _local_asset("infra/local/setup.sh")
    lines = _code_lines(setup)

    running_check = next(
        (
            index
            for index, (_, line) in enumerate(lines)
            if re.search(r"\brunning\b", line) and re.search(
                r"inspect|state|status|--format", line
            )
        ),
        None,
    )
    connect = next(
        (
            index
            for index, (_, line) in enumerate(lines)
            if "docker network connect" in line
        ),
        None,
    )

    assert running_check is not None, (
        "setup.sh must confirm each core container's state before touching it, so a "
        "stopped dependency is reported rather than worked around."
    )
    assert connect is not None, (
        "setup.sh must connect the core's containers to the local network; without it "
        "the API is on a network nothing else is on."
    )
    assert running_check < connect, (
        f"setup.sh issues `docker network connect` at line-pair {connect} but first "
        f"checks the container's state at {running_check}. Connecting a stopped "
        f"container succeeds and attaches it to a network it is not using, which "
        f"fails later as an unreachable dependency rather than as a stopped one."
    )


# ---------------------------------------------------------------------------
# The values this change copied from a shared declaration stay pinned
# ---------------------------------------------------------------------------
#
# Scoped on purpose. The estate has many declarations copied into many projects, and
# the general problem is recorded in `tasks.md` §17.7 and §17.8. What this change owns
# is exactly one thing: the values in `.env.example` that were READ from the core's own
# declarations rather than chosen here. Those must stay traceable, because a published
# port that changes underneath this file turns native mode into a connection error with
# no code change to blame.

#: Values in `.env.example` whose value came from a shared declaration, and the pin
#: that must accompany them. Populated from the file itself below; this is the order
#: they must appear.
_PROVENANCE_SOURCES: tuple[str, ...] = ()


def _recorded_provenance() -> dict[str, str]:
    """Map source path -> recorded content hash, parsed from `.env.example`.

    The record is prose in a comment block, which is the weakest possible format, so
    the parse is deliberately strict: a source with no hash on the next line is a
    failure, not a shrug. That is the property that makes a copy announce itself.
    """
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    recorded: dict[str, str] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#") or "source:" not in stripped:
            continue
        path = stripped.split("source:", 1)[1].strip()
        # The hash is the next `content hash of the file read:` line.
        for follow in lines[index + 1 : index + 4]:
            if "content hash of the file read:" in follow:
                recorded[path] = follow.split(":", 1)[1].strip()[:12]
                break
        else:
            recorded[path] = ""
    return recorded


def test_every_shared_declaration_value_carries_a_pinned_content_hash() -> None:
    """A value read from a shared declaration must say which bytes it was read from.

    Task 6.2 already required provenance; this is the part that can fail. A comment
    naming a file, with no identifier, describes a file that keeps changing — the note
    stays true while the number goes wrong.

    The pin is a content hash rather than a commit sha because of what the sources
    actually are: the PostgreSQL declaration carries uncommitted local modifications, so
    its HEAD is not the file that was read, and the object store declaration is not
    tracked by its repository at all. A commit sha would have been a precise-looking lie
    in both cases.
    """
    recorded = _recorded_provenance()
    assert recorded, (
        f"{ENV_EXAMPLE.name} declares a value read from a shared declaration but "
        f"records no source. Task 6.2 requires the provenance; this requires the "
        f"identifier that makes it checkable."
    )

    unpinned = sorted(path for path, digest in recorded.items() if not digest)
    assert not unpinned, (
        f"these sources are named with no content hash: {unpinned}. A provenance note "
        f"without an identifier describes a file that keeps changing."
    )

    malformed = sorted(
        path for path, digest in recorded.items() if not re.fullmatch(r"[0-9a-f]{7,40}", digest)
    )
    assert not malformed, f"these recorded pins are not content hashes: {malformed}"


def test_recorded_pins_still_match_the_files_they_were_read_from() -> None:
    """Recompute each pin against the file it was read from.

    Drift is a hard failure: the source changed, the copied value is stale, and the
    published port this file relies on has moved underneath it. An absent source is a
    loud skip, not a pass and not a failure — the sources are outside this repository,
    so the comparison is only possible where the estate has been cloned.
    """
    recorded = _recorded_provenance()
    assert recorded, "no provenance recorded to verify"

    unverifiable: list[str] = []
    drifted: list[str] = []
    for path, digest in recorded.items():
        source = Path(path)
        if not source.is_file():
            unverifiable.append(path)
            continue
        actual = subprocess.run(
            ["git", "hash-object", str(source)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()[:12]
        if actual != digest:
            drifted.append(f"{path}: recorded {digest}, file is now {actual}")

    assert not drifted, (
        f"a value in .env.example was read from a declaration that has since changed: "
        f"{drifted}. Re-read the source and update the value and its pin together. A "
        f"published port that moves under this file breaks native mode with no code "
        f"change to blame."
    )

    if unverifiable:
        # Skip, loudly, rather than pass or fail.
        #
        # The sources live outside this repository, in the estate mirror, so on any
        # machine that has not cloned it the comparison cannot be made. Failing would
        # mean a suite that is permanently red on CI and on every other developer's
        # box — and the Makefile already records what happens to a gate like that: it
        # gets deleted rather than fixed. Passing silently would be the same defect as
        # a healthcheck that passes while storage is unreachable, so the skip is
        # reported with the paths, and the machine-independent half of this check —
        # that every copied value carries a pin at all — runs everywhere.
        pytest.skip(
            f"cannot compare pins, these sources are not on this machine: {unverifiable}. "
            f"The pin itself is still asserted by "
            f"test_every_shared_declaration_value_carries_a_pinned_content_hash."
        )


# ---------------------------------------------------------------------------
# 10.3 / 10.14 The functional gate
# ---------------------------------------------------------------------------

#: Values the bring-up step provisions. The gate asserts against them, so it must
#: read them from the same identifiers rather than repeating them: a copy that
#: drifts asserts against a database the gate never provisioned, and — worse — a
#: copy that happens to match ANOTHER tenant's name turns a verification step into
#: a cross-tenant write. Both look like a passing gate.
_PROVISIONED_IDENTIFIERS = ("DB_NAME", "MINIO_DEFAULT_BUCKET", "MINIO_ACCESS_KEY")


def test_gate_reads_provisioned_names_instead_of_hardcoding_them() -> None:
    """The gate must not carry its own copy of a provisioned name (§10.3)."""
    gate = _local_asset("infra/local/scripts/gate-local.sh").read_text(encoding="utf-8")

    # The values come from `.env.example` — the template that documents what
    # `make setup-local` provisions. An unset key is skipped rather than matched
    # against an empty string, which every literal would satisfy.
    provisioned = {
        match.group("key"): match.group("value")
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if (match := ASSIGNMENT_PATTERN.match(line.strip())) and match.group("value")
    }

    hardcoded = [
        f"{key}={provisioned[key]}"
        for key in _PROVISIONED_IDENTIFIERS
        if key in provisioned
        and re.search(rf"""["']{re.escape(provisioned[key])}["']""", gate)
    ]

    assert not hardcoded, (
        f"gate-local.sh hardcodes provisioned name(s) {hardcoded} as string literals. "
        "It must read them from .env — the same identifiers `make setup-local` "
        "provisioned — so it cannot drift onto a name this project does not own. A "
        "gate that verifies the wrong database is worse than no gate."
    )


def test_gate_exercises_the_application_path_not_a_test_double() -> None:
    """No sqlite, no monkeypatched client, no database client (§10.14).

    `tests/conftest.py` swaps in sqlite and patches the Minio client's internals so
    the suite runs with no dependency running. A suite that passes against that
    proves nothing about the image, so the gate must reach the real thing.
    """
    # Code lines only. The script names all three in the comment explaining why it
    # avoids them, and a guard that reads its own reasoning as a violation would
    # force that reasoning to be deleted — leaving nothing to explain the choice.
    code = "\n".join(line for _, line in _code_lines(_local_asset("infra/local/scripts/gate-local.sh")))

    forbidden = {
        "sqlite": "a substitute database that is not the one the app is configured for",
        "Minio._url_open": "a monkeypatch of the object-store client",
        "psql": "a database client standing in for the application's own path",
    }
    found = [f"{token} ({why})" for token, why in forbidden.items() if token in code]

    assert not found, (
        f"gate-local.sh reaches around the application: {found}. The gate must drive "
        "the running image over HTTP, because that is what proves the image works. "
        "These substitutions are what tests/conftest.py does, and they are exactly "
        "why the suite's green is not evidence about the image."
    )


def test_gate_writes_nothing_before_it_has_checked_its_target() -> None:
    """The target check runs before the first write (§10.2).

    Structural, for the same reason the ordering check in setup-local is: a claim in
    prose about a check running "first" is not verifiable, and the failure it
    prevents is a write into another project's tenant.
    """
    lines = _code_lines(_local_asset("infra/local/scripts/gate-local.sh"))

    # Execution order is the sequence of calls in main(), not the order the
    # functions are defined in. The `cleanup` trap holds a DELETE and is defined
    # first; counting line positions would have read that as the first write and
    # demanded the file be arranged to suit the assertion. The call list is what
    # actually runs, and it is the thing worth pinning.
    main_body = "\n".join(
        line for _, line in lines
        if re.match(r"^\s+(verify|cleanup)_[a-z_]+\s*$", line)
    )
    calls = re.findall(r"^\s*([a-z_]+)\s*$", main_body, re.MULTILINE)

    assert calls, (
        "could not read the call sequence from main(); the gate's ordering check "
        "needs it, and a gate whose order cannot be read cannot be verified"
    )
    assert "verify_targets" in calls, (
        "gate-local.sh must verify which database and bucket it targets"
    )
    assert calls[0] == "verify_targets", (
        f"main() calls {calls} — the first check must be verify_targets. Everything "
        "after it creates a ticket or uploads an object, and against an unverified "
        "target that is a write into another project's tenant."
    )


# ---------------------------------------------------------------------------
# 8.6 The committed seed rows are synthetic
# ---------------------------------------------------------------------------

#: What a real row looks like, so the guard can name what it found rather than
#: asking a reader to decide whether something is production-shaped. Each pattern is
#: a shape a real record takes and a synthetic one has no reason to imitate.
_PRODUCTION_SHAPES: tuple[tuple[str, str], ...] = (
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "an email address"),
    (r"\b\d{2}[- ]?\d{3}[- ]?\d{3}\b", "a phone-like number"),
    (r"\b(?:\d{13}|\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4})\b", "a tax-id-shaped number"),
    (r"\b(?:\d{8}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4})\b", "a card-shaped number"),
    (r"\$2[yb]k", "a bcrypt hash"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key"),
)


def test_seed_rows_are_not_production_shaped() -> None:
    """Committed seed rows carry no real identifier and no credential.

    `infra/schema.sql` is a `--schema-only` dump, so no production row exists in
    this repository to copy — which is what makes "synthetic" checkable here rather
    than a claim. The risk is a row pasted in from elsewhere later, so the guard is
    on shape: a real email, tax id, card number or password hash in a committed CSV
    is a leak regardless of whether it is this tenant's, because nobody can tell.
    """
    seed_dir = REPO_ROOT / "infra/local/seed"
    csvs = sorted(seed_dir.glob("*.csv"))
    assert csvs, (
        f"no committed seed CSVs in {seed_dir.relative_to(REPO_ROOT)}. The seed rows "
        "are committed in infra/local/seed/ and copied into the git-ignored data "
        "folder at bring-up; see infra/local/seed/README.md."
    )

    offences: list[str] = []
    for csv_path in csvs:
        for number, line in enumerate(
            csv_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            for pattern, description in _PRODUCTION_SHAPES:
                if re.search(pattern, line, re.IGNORECASE):
                    offences.append(
                        f"{csv_path.relative_to(REPO_ROOT)}:{number} looks like "
                        f"{description}: {line.strip()[:60]}"
                    )

    assert not offences, (
        f"committed seed rows contain production-shaped data:\n"
        + "\n".join(offences)
        + "\n\nSynthetic rows are recognisable on sight: `Local …` names, "
        "`EQ-LOCAL-0001` identifiers, a reserved id for the seed account. The seed "
        "account's password is not committed at all — `etl/get_hash.py` generates "
        "the hash at bring-up from .env."
    )


def test_seed_password_is_never_committed() -> None:
    """The seed account's hash is generated, never committed (§8.4).

    `infra/local/seed/fsm_users.csv` being absent is the point: a committed hash is
    a fixed salt every developer then shares, and `etl/get_hash.py` exists to
    produce a fresh one per bring-up.
    """
    seed_dir = REPO_ROOT / "infra/local/seed"
    assert not (seed_dir / "fsm_users.csv").exists(), (
        "infra/local/seed/fsm_users.csv is committed. It must not be: it would carry "
        "either a password or a fixed hash, and a fixed hash means every developer "
        "shares one password and can never re-salt. `make setup-local` generates it "
        "into the git-ignored data folder — see infra/local/seed/README.md."
    )


def test_seed_loader_allowlist_matches_the_committed_tables() -> None:
    """Every committed CSV names a table the loader will actually load.

    The allowlist in `etl/seed_db.sh` is a security boundary, so an unlisted table
    is skipped rather than loaded. A committed `labsdls.csv` would therefore be
    skipped on every run — a file that provably does nothing, discovered only by
    reading the loader's skipped-tables output.
    """
    loader = (REPO_ROOT / "etl/seed_db.sh").read_text(encoding="utf-8")

    # Both array shapes have to be read: `REFERENCE_TABLES=(uom hollidays)` is
    # inline, `BUSINESS_TABLES=(` puts one name per line. Matching only the
    # indented form reported `uom` as unloadable when it is the one table whose
    # self-reference this change had to reason about.
    allowlisted: set[str] = set()
    for array in ("REFERENCE_TABLES", "BUSINESS_TABLES"):
        body = re.search(rf"{array}=\((.*?)\)", loader, re.DOTALL)
        if body:
            allowlisted |= set(re.findall(r"[a-z_]+", body.group(1)))
    assert allowlisted, (
        "could not read either load allowlist out of etl/seed_db.sh; the check needs "
        "them and a renamed array would otherwise read as 'nothing is loadable'"
    )

    committed = {p.stem for p in (REPO_ROOT / "infra/local/seed").glob("*.csv")}
    loadable = committed & allowlisted

    assert loadable == committed, (
        f"committed seed CSVs the loader will not load: {sorted(committed - allowlisted)}. "
        "Either the table is missing from `etl/seed_db.sh`'s allowlists or the CSV "
        "should not be committed. Do not add it to the allowlist casually: that list "
        "is what stops a stray CSV from COPYing into the operational record."
    )


# ---------------------------------------------------------------------------
# 9.1 The reload watcher is scoped to app/
# ---------------------------------------------------------------------------

def test_reload_watcher_is_scoped_to_the_application() -> None:
    """`uvicorn --reload` must not watch `venv/` (Makefile `run` / `run-native`).

    Without a scope the watch count scales with the number of installed packages,
    and the resulting watch-limit failure surfaces on the next reload — minutes
    after the `pip install` that caused it, with no apparent relation. Verified
    empirically in `tasks.md` §9.6; this pins the flags so the scope cannot be
    dropped silently, which would restore the failure with no other trace.
    """
    makefile = MAKEFILE.read_text(encoding="utf-8")

    uvicorn_lines = [
        line for _, line in _code_lines(MAKEFILE) if "uvicorn" in line
    ]
    assert uvicorn_lines, "the Makefile no longer has a uvicorn target"

    unscoped = [
        line.strip()
        for line in uvicorn_lines
        if "--reload" in line and "--reload-dir" not in makefile
    ]
    assert not unscoped, (
        f"uvicorn is invoked with --reload but no --reload-dir: {unscoped}. "
        "The watcher would follow venv/ and .pytest_cache/, and the watch limit "
        "would be hit by an ordinary pip install."
    )

    for target in ("run:", "run-native:"):
        assert target in makefile, f"the Makefile lost its {target[:-1]} target"
    assert makefile.count("--reload-dir app") >= 2, (
        "both `run` and `run-native` must scope the watcher with --reload-dir app; "
        "one of them was left watching the whole repository"
    )


# ---------------------------------------------------------------------------
# Regressions found by running the stack, not by reading it
# ---------------------------------------------------------------------------
#
# Every test below guards a defect that passed the whole suite and then failed on
# a live database. They are grouped because they share a cause worth naming: the
# suite could only check what these scripts SAY, never whether the sentence was
# true. A gate that asserts the wrong enum label, addresses its token to the wrong
# scope, or reads a revision with a pattern that cannot match the history it is
# reading is not a slow check, it is a check that reports something else.

SETUP_SH = _local_asset("infra/local/setup.sh")
GATE_SH = _local_asset("infra/local/scripts/gate-local.sh")
MIGRATE_LIB = _local_asset("infra/local/scripts/lib-migrate.sh")
LOCAL_SCHEMA = REPO_ROOT / "infra" / "schema.sql"


def _shell_code(path: Path) -> str:
    """A shell script with its full-line comments removed.

    These assertions describe what the script DOES. Several of them name the
    broken pattern in prose, so matching the raw text finds the explanation of the
    bug instead of the bug.
    """
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_provisioning_reapplies_grants_when_the_role_already_exists(tmp_path: Path) -> None:
    """A surviving role must not mean a surviving grant (§3.4, proven live).

    Roles are cluster-wide and grants live inside a database, so dropping and
    recreating this project's database keeps `gestiket_app` and takes every grant
    with it. The first version skipped the whole template whenever the role
    existed, which made that sequence produce a role that authenticates and can do
    nothing: login returned 500 with `permission denied for table fsm_users`, and
    the cause was a branch in this script several steps earlier.

    The stripper is executed here rather than pattern-matched, because the failure
    this guards against is a *partial* removal: dropping only the `CREATE ROLE`
    line leaves the `NOINHERIT`/`PASSWORD` continuation dangling and psql reports
    a syntax error that names nothing useful.
    """
    setup = SETUP_SH.read_text(encoding="utf-8")

    stripper = re.search(r"awk '\n(?P<program>.*?)\n\s*' \"\$PROVISION_SQL\"", setup, re.S)
    assert stripper, (
        "setup.sh no longer strips CREATE ROLE from the substituted template. "
        "Re-applying the template to an existing role is only safe because that "
        "one statement is removed; without the stripper the run fails on a role "
        "that already exists."
    )

    substituted = (
        "CREATE ROLE gestiket_app WITH LOGIN PASSWORD 'secret' NOSUPERUSER NOINHERIT;\n"
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO gestiket_app;\n"
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO gestiket_app;\n"
    )
    fixture = tmp_path / "provision.sql"
    fixture.write_text(substituted, encoding="utf-8")

    applied = subprocess.run(
        ["bash", "-c", f"awk '{stripper.group('program')}' {fixture}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert "CREATE ROLE" not in applied, (
        f"the stripper left CREATE ROLE in the executable template:\n{applied}"
    )
    for statement in ("GRANT SELECT ON ALL TABLES", "ALTER DEFAULT PRIVILEGES"):
        assert statement in applied, (
            f"the stripper removed {statement!r} as collateral. Only CREATE ROLE may "
            f"be dropped; everything else in the template is the idempotent grant "
            f"work this run exists to redo.\napplied template:\n{applied}"
        )

    # And the template is executed from the stripped file, not from the original.
    assert '< "$PROVISION_APPLY"' in setup, (
        "setup.sh must execute the stripped template. Feeding psql the unstripped "
        "file would re-introduce the duplicate-role failure the stripper prevents."
    )


def test_gate_uses_a_token_every_later_check_can_reach() -> None:
    """The auth token is shared state, not a local of the function that made it.

    It was declared `local token` in the login step and read as `${token}` by the
    upload steps. Under `set -u` that is `token: unbound variable`, so the gate
    stopped at the first write — after reporting a passing login.
    """
    gate = _shell_code(GATE_SH)

    assert not re.search(r"\$\{token(?::-|})", gate), (
        "gate-local.sh reads `${token}` (lowercase). The shared token is TOKEN; a "
        "lower-case name is a function-local, invisible to every later check, and "
        "aborts the gate under `set -u`."
    )
    assert not re.search(r"local [^\n]*\btoken\b", gate), (
        "gate-local.sh declares `token` local to one function while other "
        "functions depend on it."
    )
    assignments = re.findall(r"^\s*TOKEN=", gate, re.M)
    assert assignments, (
        "TOKEN is never assigned; the checks have nothing to authenticate with."
    )
    # Scope, not spelling. `local TOKEN=…` reads correctly and is invisible to
    # every other function, which is the original defect with the capitalisation
    # fixed — the failure moves rather than disappearing.
    assert not re.search(r"^\s*local\s+TOKEN=", gate, re.M), (
        "TOKEN is assigned as a function-local. The write, upload and delete steps "
        "are separate functions and cannot see it; under `set -u` the first of them "
        "aborts with an unbound-variable error."
    )


def test_gate_writes_enum_labels_the_schema_actually_declares() -> None:
    """`priority` and `status` are enum columns, so the gate's literals must match.

    Lowercase `"low"` reached PostgreSQL and came back as `invalid input value for
    enum priority_type`, surfacing as a 500 whose only visible cause was a string
    in a test fixture. The labels are read from the schema, so changing an enum
    there fails this test instead of the next live run.
    """
    schema = LOCAL_SCHEMA.read_text(encoding="utf-8")
    declared = {
        enum_type: set(re.findall(r"'([^']+)'", body))
        for enum_type, body in re.findall(
            r"CREATE TYPE public\.(\w+) AS ENUM \((.*?)\);", schema, re.S
        )
    }

    for enum_type in ("priority_type", "status_type"):
        assert enum_type in declared, (
            f"the schema no longer declares {enum_type}; the gate's fixture must be "
            "re-checked against whatever replaced it"
        )

    labels = declared["priority_type"] | declared["status_type"]
    used = {
        match.group("field"): match.group("value")
        for match in re.finditer(
            r'"(?P<field>priority|status)":"(?P<value>[^"]+)"', _shell_code(GATE_SH)
        )
    }
    assert used, "no enum-valued field found in the gate's ticket payload"

    for field, value in used.items():
        assert value in labels, (
            f"the gate posts {field}={value!r}, which is not a label of the enums "
            f"this schema declares. PostgreSQL rejects it at insert time, so the "
            f"gate fails with a 500 instead of checking what it meant to check. "
            f"Declared labels: {sorted(labels)}"
        )


def test_gate_uploads_against_a_parent_row_that_exists() -> None:
    """The upload parent must be a real maintenance, not a synthetic id.

    `POST /uploads/init` does not read its parent, so a fixed UUID passed that step
    and failed at `complete`, which does — 404 on `maintenances ... no longer
    exists`. `maintenances` is also the only domain table whose primary key is a
    UUID; every other entity uses an integer id, which Pydantic rejects outright.
    So the gate creates the maintenance through the API and deletes it afterwards.
    """
    gate = GATE_SH.read_text(encoding="utf-8")

    assert not re.search(r'GATE_PARENT_ID\s*=\s*"[0-9a-f-]{36}"', gate), (
        "gate-local.sh hardcodes a UUID as the upload parent. Nothing creates that "
        "row, so `complete` 404s on it."
    )
    assert "parent_id" in gate and "CREATED_MAINTENANCE_ID" in gate, (
        "the upload's parent_id must come from the maintenance this run created."
    )
    assert re.search(r"POST \"\$\{API_BASE\}/maintenances\"", gate), (
        "the gate must create the parent maintenance through the API, so the id is "
        "one the application produced rather than one invented here."
    )
    assert "DELETE /maintenances" in gate or "/maintenances/${CREATED_MAINTENANCE_ID}" in gate, (
        "the maintenance created for the upload must be deleted again; the gate "
        "leaves the database as it found it."
    )


def test_gate_removes_the_uploaded_object_by_key() -> None:
    """`remove_object` needs the bucket-relative key, not the presigned URL.

    The URL carries scheme, host, bucket and signature. Passing it whole made the
    removal fail on every run — and it failed as a warning, so each run silently
    added one more object to the bucket, under a path named for a ticket the gate
    had already deleted.
    """
    gate = GATE_SH.read_text(encoding="utf-8")

    assert not re.search(r'CREATED_OBJECT_KEY="\$\{file_url\}"', gate), (
        "CREATED_OBJECT_KEY must not be the presigned URL; MinIO needs the key."
    )
    for strip in ('${file_url#*://*/}', '${object_path%%\\?*}'):
        assert strip in gate, (
            f"the object key derivation lost {strip!r}. Scheme/host and the "
            "signature query string must both be removed, or the removal targets "
            "an object that does not exist."
        )
    assert '${CREATED_OBJECT_KEY}' in gate, (
        "remove_object must be given CREATED_OBJECT_KEY."
    )


def test_gate_reports_failure_and_cleans_up_without_a_tty() -> None:
    """CI is not a terminal: the trap must not be conditional on one.

    Colour is a TTY concern. The failure summary is not — hiding it behind
    `[ -t 1 ]` meant a failing gate in CI printed nothing but the FAILED line.
    The same handler removes what the run created, because a run that dies between
    creating rows and deleting them leaves a primary key behind and the NEXT run
    fails on `duplicate key value ... tickets_pkey` — blaming the ticket id
    instead of whatever broke the first run.
    """
    gate = _shell_code(GATE_SH)

    colour_block = re.search(r"if \[ -t 1 \][\s\S]*?\nfi\n", gate)
    assert not (colour_block and "trap" in colour_block.group(0)), (
        "the EXIT trap is inside a `[ -t 1 ]` branch. Move it out and leave only "
        "the colour variables conditional, or CI failures print no summary."
    )
    armed = re.search(r"^trap (?P<handler>\w+) EXIT", gate, re.M)
    assert armed, "the EXIT trap must be armed unconditionally"

    handler = re.search(
        rf"^{armed.group('handler')}\(\) \{{(?P<body>[\s\S]*?)^\}}", gate, re.M
    )
    assert handler, f"the trap names {armed.group('handler')}, which is not a function here"
    assert re.search(r"\bcleanup\b", handler.group("body")), (
        f"{armed.group('handler')} does not call cleanup; otherwise a failed run "
        "leaves rows that break the next one."
    )
    assert re.search(r"remove_object", handler.group("body")), (
        f"{armed.group('handler')} does not remove the uploaded object; a failed run "
        "would leave it in the bucket, which is shared."
    )
    assert "CREATED_MAINTENANCE_ID=\"\"" in gate, (
        "the maintenance id must be cleared after it is deleted, or cleanup removes "
        "a row twice."
    )


def test_both_local_scripts_share_one_migration_environment_helper() -> None:
    """The env-forwarding rules live in one file, not twice.

    The list is long and the rules are subtle: forward every required setting,
    except those the compose file already declares for the container, and replace
    the database credential with the elevated one. Written twice it drifts, and the
    failure is a migrate job that dials loopback from inside the network and is
    refused — which is how it was found the first time.
    """
    setup = SETUP_SH.read_text(encoding="utf-8")
    gate = GATE_SH.read_text(encoding="utf-8")
    lib = MIGRATE_LIB.read_text(encoding="utf-8")

    for name, script in (("setup.sh", setup), ("gate-local.sh", gate)):
        assert "lib-migrate.sh" in script, (
            f"{name} must source infra/local/scripts/lib-migrate.sh for the migrate "
            "environment instead of carrying its own copy."
        )
        assert "compose_owned_keys" not in script, (
            f"{name} re-implements the compose-owned-key exclusion. Two copies of "
            "that list is how one of them ends up missing a key."
        )

    assert 'export "${key}=${value}"' in gate, (
        "the gate must export what it reads from .env: `docker compose run -e KEY` "
        "takes its value from the process environment, so an unexported shell "
        "variable is invisible and the migrate job starts with none of them."
    )
    assert "CORE_DB_ADMIN_USER CORE_DB_ADMIN_PASSWORD" in gate, (
        "alembic_version is not readable by the runtime role, so the gate needs the "
        "elevated credential to report the revision."
    )


def test_no_local_script_matches_revisions_by_the_shape_of_a_hex_id() -> None:
    """This history uses named revisions; a hex pattern matches nothing.

    `alembic current` reported `unknown revision` against a database that was
    perfectly current at `0003_join_table_keys`, because the summary grepped for
    `[0-9a-f]{7,}`. Alembic marks heads with a literal `(head)`, which is
    revision-format independent.
    """
    for path in (SETUP_SH, GATE_SH, MIGRATE_LIB):
        content = _shell_code(path)
        assert "[0-9a-f]{7,}" not in content, (
            f"{path.name} matches a revision with a hex-only pattern. This history "
            "uses named revisions such as 0003_join_table_keys, which that pattern "
            "cannot match; use alembic's own '(head)' marker."
        )
    assert r"\(head\)" in _shell_code(MIGRATE_LIB), (
        "the shared helper must read the revision from alembic's '(head)' marker."
    )


def test_grants_are_applied_after_the_schema_and_migrations() -> None:
    """Provisioning grants on tables BY NAME, so it must come after they exist.

    The canonical template says so itself -- "Existing objects are not covered by
    ALTER DEFAULT PRIVILEGES ... this is why the roles are provisioned AFTER the
    schema of record is loaded" -- and the local setup had it backwards. Against a
    freshly created, still empty database the template failed on `relation
    "adticketswkd" does not exist`, and only a machine that already had a populated
    database could hide that.

    The quieter half of the same hazard is worse. `ALTER DEFAULT PRIVILEGES` sits
    ABOVE the failing GRANT, so the failed run still left a default ACL granting
    SELECT/INSERT/UPDATE/DELETE on every future table. The next run then loaded the
    schema, and every table it created inherited those privileges -- including the
    six the template exists to withhold. The role ended up able to read `uom`,
    `alembic_version`, `materials`, `preliquidated`, `services` and `holidays`, and
    nothing anywhere reported an error.
    """
    setup = _shell_code(SETUP_SH)

    main = re.search(r"^main\(\) \{[\s\S]*?^\}", setup, re.M)
    assert main, "setup.sh no longer has a main() to order the steps in"
    body = main.group(0)

    positions = {
        step: body.find(step)
        for step in ("ensure_database", "apply_schema", "run_migrations", "provision_database")
    }
    for step, position in positions.items():
        assert position != -1, f"{step} is not called from main()"

    assert positions["ensure_database"] < positions["apply_schema"], (
        "the database must be created before the schema is applied to it"
    )
    assert positions["apply_schema"] < positions["provision_database"], (
        "the schema must exist before the template grants on tables by name"
    )
    assert positions["run_migrations"] < positions["provision_database"], (
        "migrations must run before provisioning: migration 0001 creates "
        "token_blacklist, which the template grants on explicitly."
    )


def test_local_setup_never_grants_more_than_the_canonical_template_lists() -> None:
    """The withheld tables must stay withheld, and that is checkable statically.

    The template grants SELECT/INSERT/UPDATE/DELETE on a NAMED list of 17 tables
    out of 23. Anything wider -- `ON ALL TABLES`, a default ACL applied before the
    schema load -- silently hands the running service the other six, and no step
    reports anything. Asserting the count and the absence of a blanket grant keeps
    the local stack inside the same boundary the VPS template defines.
    """
    template = (REPO_ROOT / "infra" / "provision" / "001-create-application-roles.sql").read_text(
        encoding="utf-8"
    )

    # The newline after ON is what distinguishes the named table list from
    # `ALTER DEFAULT PRIVILEGES ... GRANT ... ON TABLES TO ...`, which has the
    # same privileges and a single table named TABLES.
    granted = re.search(
        r"GRANT SELECT, INSERT, UPDATE, DELETE ON\s*\n(?P<tables>[a-z_, \n]+?)\s*TO\s",
        template,
    )
    assert granted, "the canonical template no longer grants DML on a named table list"

    named = {name.strip() for name in granted.group(1).split(",") if name.strip()}
    assert len(named) == 17, (
        f"expected the canonical list of 17 tables, found {len(named)}: {sorted(named)}"
    )

    setup = _shell_code(SETUP_SH)
    # A GRANT STATEMENT, not the word: the script legitimately mentions GRANT when
    # checking that the stripped template still contains its grants.
    assert not re.search(r"(?m)^\s*GRANT\s+[A-Z]", setup), (
        "setup.sh issues a GRANT of its own. The canonical template is the single "
        "definition of what the runtime role may do; a grant here would grant "
        "something the VPS role does not have, and the two environments would "
        "quietly diverge."
    )


def test_gate_removes_the_photo_rows_the_upload_leaves_behind() -> None:
    """A gate that grows a table on every run is a gate people stop running.

    Completing an upload inserts into `photos` and the row survives the gate: the
    service stores the path but leaves `maintenance_id` NULL, so
    `DELETE /maintenances/{id}` cannot reach it, and the foreign key is NO ACTION.
    Measured on this project's own database: photos went 1 -> 2 -> 3 across
    consecutive runs, and nothing reported it.

    The rows are matched on the ticket id inside the stored path, which is what
    keeps the delete inside this project's own data on a shared core.
    """
    gate = _shell_code(GATE_SH)

    assert re.search(r"DELETE FROM photos", gate), (
        "gate-local.sh does not remove the photo rows its uploads create. Nothing "
        "else does either -- the maintenance delete cannot reach them -- so each "
        "run leaves one behind."
    )
    assert "photo_path LIKE" in gate, (
        "photo rows must be matched on the stored path, which carries the ticket id. "
        "That is what scopes the delete to this project's own uploads."
    )
    assert re.search(r"TICKET\s*=\s*\"\$\{GATE_SEED_TICKET_ID\}\"", gate), (
        "the photo sweep must be scoped by the gate's own ticket id, never by a "
        "blanket DELETE, which on a shared core would be another tenant's data."
    )
