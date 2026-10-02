## Why

Several of this developer's own projects consume one shared PostgreSQL and MinIO core, on
this machine and on the VPS, and this project is one of them. Nothing in this repository
says so. Getting a working local environment means leaving it: `README.md:31-36` and
`docs/development_guide.md` §3.5 tell the developer to `cd` into another project, run
commands they cannot see the results of, and hand-edit `.env` values copied from that
project's files. The dependency is real, load-bearing, and entirely undocumented.

That leaves the shared core as the local topology **and** the deployed topology, which is
the right outcome, arrived at by accident and by no documented step. There is no bring-up
command, no record of which port or database name this project is supposed to use, and no
test that would fail if it were the wrong one. So a developer who has it wrong sees
connection errors, or worse, sees nothing wrong because they happened to land on the right
values.

The verification that does exist is aimed at the wrong moment. `Dockerfile:98` declares a
`HEALTHCHECK` on `/openapi.json`, which touches neither PostgreSQL nor MinIO; the
application has no health or readiness route at all; and `tests/conftest.py:20-24`
substitutes SQLite and stubs `Minio._url_open`, so the suite passes against neither
dependency either. A green test run and a healthy container therefore both say nothing
about whether the stack works.

## What Changes

- **Consume the shared core locally instead of declaring a second one.** This project
  declares no PostgreSQL service, no object-store service and no data volume. It declares
  only its own API, and it reaches the core the way the VPS does — as a consumer. The root
  `docker-compose.yml`, everything in `infra/vps/`, and the core project's own declaration
  in the sibling repository are left alone.
- **Isolate by database, role and bucket, not by instance.** The core is shared with several
  other applications, so this project gets its own role, its own database, its own bucket
  and its own credentials on it — the same arrangement the VPS already uses. It joins the
  core's network as a consumer and mounts none of its volumes. Joining a shared network is
  how a consumer reaches a shared dependency; what is forbidden is *declaring your own copy
  of a shared dependency and* joining the shared network, or borrowing a shared container's
  name, either of which makes name resolution ambiguous.
- **Add one orchestrated bring-up** (`make setup-local`) that starts the shared core,
  provisions this project's role, database and bucket, and migrates — failing with a
  message naming the missing prerequisite rather than a connection error from the
  application. Provisioning is additive and confined to this project: it creates objects and
  edits no shared configuration file. It does not touch `pg_hba.conf` and does not restart
  the core's containers, because both would change behaviour for consumers of an instance
  this project does not own.
- **Add a committed example env** for local values. The file name stays `.env` — the same
  name the VPS already uses (`infra/vps/docker-compose.yml:61`) — so there is one env
  format in every environment and only the values differ. Every value copied from the
  core's declaration records where it was read from, because a copied value without its
  provenance outlives the thing it was copied from. No local compose key is written into
  `infra/vps/`.
- **Remove the environment-varying defaults from `app/core/settings.py`.** Today
  `pg_port`, `minio_port`, `minio_secure`, `minio_region`, `minio_default_bucket`,
  `base_object_path`, `templates_dir`, `chunk_dir`, `pdf_suffix` and `presigned_ttl_hours`
  all have defaults, and `minio_public_*` falls back component-wise to the internal
  values (`settings.py:198-214`). A local environment that forgets one value starts
  successfully against the wrong target. **BREAKING**: a `.env` that omits a now-required
  key aborts the process at import instead of defaulting.
- **Make the shipped image safe to run locally**: add a non-root `USER` to the runtime
  stage and stop installing development tooling into it. The runtime stage currently has
  no `USER` at all and installs `gcc`, `libpq-dev`, `pytest`, `pytest-cov`, `pytest-asyncio`,
  `factory_boy`, `httpx` and `pandas`. **BREAKING** for the running image: this is a change
  to what ships.
- **Add a deterministic local seed** (`infra/local/seed.sql` plus a bring-up script) that
  creates only structurally faithful reference rows, in this project's own database and
  bucket. No production data in any form. No credential in any committed file: the seed
  user's password is read from the developer's git-ignored `.env`, never from a committed
  default.
- **Add a functional gate** (`make gate-local`) that proves the built image works: an
  authenticated read, a write, and a round trip through the application's own MinIO client,
  plus two image assertions (the container does not run as root; it carries no development
  tooling). It first asserts that the resolved connection names this project's own database
  and its own bucket, and aborts without writing if it does not — because the gate mutates
  a shared instance. Output is a fixed block designed to be pasted into a release note.
- **Fix the file-watcher scope.** `Makefile:111` runs `uvicorn --reload` with no
  `--reload-dir`, so it watches the whole tree including `venv/` and `.pytest_cache/`.
  A dependency install therefore exhausts the OS watch limit and the failure appears later,
  unconnected to its cause.
- **Do not include Caddy locally**, and specify what verifies the media path instead.
- **State the limits of a local check**: it is not a staging environment, and it does not
  exercise the VPS network, the TLS origin, or VPS scheduling.

### Not in scope

- Any edit to `infra/vps/docker-compose.yml` or `infra/vps/Caddyfile`.
- Any edit to `infra/schema.sql` or `infra/provision/`.
- Any edit to the core project's own compose file, image definition, or network, in the
  sibling repository. This change consumes them. A file that lives in another project is
  still a file a careless edit would reach, so it is listed here.
- Declaring this project's own PostgreSQL or object store, and declaring its own copy of a
  shared dependency anywhere.
- Applying the VPS's connection-level isolation locally, which would mean editing a shared
  configuration file and restarting a shared container.
- Building the image on the target host. Producing an artifact on one host and running it
  on another is a separate change; recorded here only as a dependency.

## Capabilities

### New Capabilities

- `local-stack-environment`: the local service topology, which services run natively
  versus which are consumed, the local port and hostname table recorded against the VPS
  values, one configuration code path with no undecided defaults, loopback and
  name-resolution rules for reaching PostgreSQL and MinIO, the rules for consuming a shared
  dependency without providing a competing one, exclusion of Caddy, and file-watcher scope.
- `local-data-provisioning`: how this project's own role, database and bucket are created
  on the shared core — the shared schema of record, the shared migration image stage, the
  PostgreSQL extension the schema needs, a deterministic seed with no production data and no
  committed credentials, and the rule that provisioning is additive, confined to this
  project, and edits no shared configuration file.
- `local-functional-gate`: the pre-release verification command, its three functional
  checks, its two image assertions, its own-database and own-bucket precondition, its
  expected output, and its stated limits.

### Modified Capabilities

None. `openspec/specs/` holds `user-auth`, `master-data-api` and `photo-replace-delete`;
none of their requirements change. No endpoint is added, removed or altered.

## Impact

**Blast radius — files shared by dev and VPS, with a stated decision for each:**

| File                                                                                           | Shared with                                      | Decision                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Dockerfile`                                                                                   | VPS build (`infra/vps/docker-compose.yml:42-45`) | **Edit.** Add `USER`, remove dev tooling. Risk and rollback stated in the task.                                                                           |
| `requirements.txt`                                                                             | both image stages, VPS runtime                   | **Split.** New `requirements-dev.txt`; the runtime image stops installing test packages. Risk: the `migrate` stage must keep `alembic`.                   |
| `app/core/settings.py`                                                                         | every process in every environment               | **Edit.** Remove environment-varying defaults. Risk: a VPS `.env` missing a key now aborts at boot instead of defaulting. Rollback: restore the defaults. |
| `.env.example`                                                                                 | template for both environments                   | **Edit.** Add a documented local section. It is a template; the VPS `.env` is a copy, so no deployed value changes.                                       |
| `infra/schema.sql`                                                                             | VPS `docs/deployment-guide.md` §2.2, and the local schema on the core | **No edit.** A guard test asserts it still loads cleanly for both.                                                                    |
| `infra/provision/001-create-application-roles.sql`                                             | VPS §2.1, and the local role on the core            | **No edit.** Local reuses it with substituted placeholders, so local holds the same least-privilege role.                                                 |
| `alembic/`                                                                                     | VPS `migrate` job                                | **No edit.**                                                                                                                                              |
| `tests/test_deploy_assets.py`, `tests/test_provisioning.py`, `tests/test_skill_agnosticism.py` | read `Dockerfile`, `infra/vps/`, and skill prose | **No edit.** They may need new sibling assertions, and the implementer must keep them passing.                                                            |
| `Makefile`                                                                                     | dev only                                         | **Edit.** `--reload-dir app` plus new targets.                                                                                                            |

**New files:** `infra/local/docker-compose.yml` (the API and the `migrate` job only),
`infra/local/setup.sh` or equivalent bring-up, `infra/local/seed.sql`,
`infra/local/scripts/`, the local section of `.env.example`, `requirements-dev.txt`, and
the gate script.

**Out of scope and unchanged:** `infra/vps/**`, `docs/deployment-guide.md`, the root
`docker-compose.yml`, `bootstrap.sh`, `core/**`, `etl/**`, the core project's own
declaration in the sibling repository, and the API contract (`docs/api-spec.yml` /
`.json` — no endpoint changes, so no re-export is required).

**Writes outside this repository, and the one rule for them.** This change adds state to the
shared core: a role, a database, a bucket, a user and this project's credentials on an
instance other projects also use. Every such object is additive and named for this project,
and none of them is created by editing a shared configuration file or restarting a shared
container. Reverting this change does not remove that state, and must not: the objects belong
to the project, not to the change.

**Known repository defects this does not fix:** `TICKET-007` (the custom PostgreSQL image
is only defined in `core/postgres-gci/Dockerfile`, which no document cites),
`TICKET-016` (`bootstrap.sh` cannot complete), `TICKET-019` (models are 94 operations
stale against the live database, so autogenerate is destructive), `TICKET-018` (5 tables
exist with no model). Local schema therefore comes from `infra/schema.sql` plus Alembic
`upgrade head`, never from autogenerate.

**A separate verification pass — over both the files and the container engine — established
which side of a known divergence is live.** `core/compose.yml` in this repository has drifted
from a counterpart that is actually running in `~/Documents/GoogleCloudProjects/`: different
service key, and a published port that disagrees on both value and interface binding. The
engine settled it. The running `postgres-gci` container's own labels name the sibling
project's root compose file as the declaration that created it, so this repository's copy is
not the file that produced the running container.

Two findings from that pass change what this change has to do, and are the reason it is not
the private-stack design it was first drafted as:

- **The core already runs on this developer's machine.** All 19 containers here are stopped,
  but a stopped container still holds its published port, its volumes and its network. So
  the estate's PostgreSQL and MinIO are available locally as containers — they simply are not
  brought up, described or verified by anything in this repository. That is a documentation
  and orchestration gap, not a missing service, and closing it needs no new dependency and no
  second copy of anything.
- **The shared core's own definition solves a problem this change would have had to solve.**
  `infra/schema.sql:113` requires `pg_uuidv7`, which stock `postgres:16` does not provide and
  which no document cites a buildable definition for; the running container's image is a
  project-scoped build that does provide it. Consuming the core therefore removes the local
  image decision entirely. `TICKET-007` remains open for the estate, but it is no longer this
  change's problem to work around.

Both are recorded in `design.md` and the follow-up tasks rather than addressed here, because
neither is a divergence this change introduces nor a file it is positioned to fix.
