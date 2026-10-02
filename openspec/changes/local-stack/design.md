## Context

### What exists today

`app-tickets-backend` runs on a VPS. PostgreSQL and MinIO are shared with other tenants;
this project owns only the API and a TLS edge. The deploy contract lives in
`infra/vps/docker-compose.yml` (project `app-tickets-vps`) and `infra/vps/Caddyfile`, and
the procedure lives in `docs/deployment-guide.md`.

There is no local stack. Every developer-facing path is broken or points outside the tree:

- The root `docker-compose.yml` declares no services. Its only `include` is commented out,
  and the comment explains the containers now live in other projects. `docker compose up`
  there is a no-op.
- `bootstrap.sh` cannot finish. Its last action is `cd "$PROJECT_ROOT/gtk-companies/gtk-base"`
  (line 136), a directory deleted on 2026-09-30. It also `docker start postgres-gci`
  (line 79), a container this repository no longer owns.
- `README.md:38-49` and `docs/development_guide.md:20-36` instruct the developer to `cd`
  into `~/Documents/GoogleCloudProjects` to start PostgreSQL and MinIO. Neither is in the
  tree. `docs/development_guide.md` also tells the developer to run `docker compose up -d
  postgres`, a service the root compose never defined.
- `core/compose.yml` is the last in-tree attempt at a local PostgreSQL. It is inert: its
  volumes point at three directories that do not exist, its port (`5433:5432`) contradicts
  the documented `5435`, and its service key (`postgres-gtk`) contradicts everything else.

### Existing infrastructure: where it was searched, and what that search found

This search was **not performed in the current flow**. It was a separate verification pass,
run after the initial artifacts were drafted, whose purpose was to establish which
components this repository still owns versus which have moved to sibling projects. Its
findings are recorded here because several of them change how `core/` must be reasoned
about. Nothing in the current flow depends on the sibling repositories being present at
implementation time.

The search covered **two sources**: the files on disk, and the container engine. The engine
search was the decisive one — it answered which of two competing `core/compose.yml` files
was live without either file containing that information.

#### Source 1: files on disk

| Location searched | Contents found |
|---|---|
| `docker-compose.yml` (root) | No services. `include` entries all commented out. |
| `core/compose.yml` | **Two** services: `postgres-gtk` (`container_name: postgres-gci`) and `pgadmin-gci`. **No MinIO, no Caddy.** |
| `core/postgres-gci/`, `core/pgadmin-gci/` | The only in-tree definitions: the 4-line `pg_uuidv7` image build, and pgadmin's image. |
| `infra/vps/` | Caddy (`docker-compose.yml:172` + `Caddyfile`), the API, and the `migrate` job. **This is where Caddy lives**, not in `core/`. |
| `~/Documents/GoogleCloudProjects/` | A live sibling project. Its root `docker-compose.yml` is an 11-line orchestrator that only `include`s `./core/compose.yml`, and defines MinIO at `gci-companies/gci-empresa-a/assync/docker-compose.yml`. |

Two corrections to the assumption that `core/` holds all three components:

- **MinIO is not in `core/`.** It is defined only in the sibling project, at
  `~/Documents/GoogleCloudProjects/gci-companies/gci-empresa-a/assync/docker-compose.yml`.
  No MinIO compose definition exists anywhere in this repository.
- **Caddy is not in `core/`.** It is in `infra/vps/`, which this change already treats as
  the no-touch VPS-only set. Decision 6 is therefore unaffected: Caddy was excluded locally
  because of what it does, not because of where it lives.

#### Source 2: the container engine

`docker ps -a` lists **19 containers** across 8 unrelated compose projects, all in state
`Exited`. None is running at the time of the search. The three relevant to this change:

| Container | Image as built | Created by (working dir) | Network | Data volume |
|---|---|---|---|---|
| `postgres-gci` | `infrastructure-companies-postgres-gci` | `~/Documents/GoogleCloudProjects` via its root `docker-compose.yml` | `infrastructure-companies_gci-db-network` | `infrastructure-companies_postgres-gci-data` |
| `pgadmin-gci` | `infrastructure-companies-pgadmin-gci` | same project, same root file | same network | its own volume |
| `minio-acme` | `quay.io/minio/minio:latest` | `~/Documents/GoogleCloudProjects/gci-companies/gci-empresa-a/assync` | `assync_as-sync-acme-network` | `assync_acme_minio_data` |

Four facts came only from the engine:

1. **`postgres-gci` was created from the sibling's root `docker-compose.yml`**, whose own
   label names `infrastructure-companies` as the compose project. That file `include`s the
   sibling's `core/compose.yml`. So the sibling's file is the live declaration and **this
   repository's `core/compose.yml` is not the one that produced the container**, despite
   sitting in this repository. Two `core_gci-db-network` and
   `infrastructure-companies_gci-db-network` networks exist; only the latter has members.
2. **The container's binds mount four paths** — `/backups`, `/docker-entrypoint-initdb.d`,
   `/etc/postgresql/pg_hba.conf`, `/etc/postgresql/postgresql.conf` — with **empty source
   values in the inspect output**, because the paths are supplied by variables resolved
   from the sibling project's `.env`. This confirms from the outside what `docker compose
   config` showed from the inside: this repository's `PROJECT_ROOT` resolves over there.
3. **MinIO takes its credentials from mounted files, not environment values.**
   `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` are both empty strings; the actual values
   arrive via `MINIO_ROOT_USER_FILE` and `MINIO_ROOT_PASSWORD_FILE`. A configuration
   inventory that only reads environment values concludes this deployment has no
   credentials, which is the opposite of the truth. MinIO also publishes
   `MINIO_PUBLIC_ENDPOINT=127.0.0.1`, `MINIO_PUBLIC_PORT=9000`, `MINIO_PUBLIC_SECURE=false`
   — the same public-origin shape this change's Decision 5 sets for local, which is
   evidence the shape is already the estate's convention rather than a local invention.
4. **Every container is stopped, yet all of them still hold their ports, volumes and
   network names.** `5435`, `9000` and `9001` are held by stopped containers that any of
   the 19 could re-claim. This is why the local ports in Decision 2 are chosen to collide
   with none of them, and why the local compose must bind explicitly to loopback rather
   than letting the runtime pick.

Two further observations recorded but not acted on: the MinIO image is `:latest`, so the
"no recorded MinIO version" gap in either project is real — the tag is unpinned; and
`docker inspect` on `postgres-gci` reports no published port, consistent with the compose
file binding `127.0.0.1:5435` for the benefit of host-side callers rather than containers.

`core/postgres-gci/Dockerfile` is byte-identical in both locations, and the engine confirms
the image was built from the sibling's copy of it (`infrastructure-companies-postgres-gci`).
That file is the only artifact here this change reuses, and it is load-bearing:
`infra/schema.sql:113` executes `CREATE EXTENSION IF NOT EXISTS pg_uuidv7`.

#### Reconciling the two sources

| | this repository | sibling project (live, per engine labels) |
|---|---|---|
| service key | `postgres-gtk` | `postgres-gci` |
| `container_name` | `postgres-gci` | `postgres-gci` |
| published port | `5433:5432`, all interfaces | `127.0.0.1:5435:5432`, loopback |
| produced the running container | no | yes |

**This repository's `core/compose.yml` is a fork of a file that is still live elsewhere**,
not a stale copy of something retired. It has already drifted on the service key and the
published port, and the running container proves which side is authoritative.

Consequence for this design: the reason not to reuse `core/compose.yml` is now stronger than
"it is stale". It has *already* drifted from a live counterpart, so editing it here would
re-diverge it and would appear to fix a file the sibling project still depends on. Decision
11 stands unchanged — build the local service from the shared image definition, do not
inherit the compose file.

**Recorded, not acted on.** The divergence between the two `core/compose.yml` files, the
unpinned `:latest` MinIO tag, and the fact that no project records which of them owns that
file, are out of scope for this change. They are listed in the follow-up task group rather
than fixed, because fixing them means deciding whether this repository still owns a copy of
that file at all — a question this change has no stake in.

### How configuration is actually resolved

One path, already correct in shape: `app/core/settings.py:216` instantiates a single
`Settings` from `ROOT_DIR/.env`, and `alembic/env.py:41` overwrites Alembic's URL with
`settings.pg_dsn`, so migrations and the app read the same values. Nothing branches on
environment.

What is wrong is the defaults. `pg_port`, `minio_port`, `minio_secure`, `minio_region`,
`minio_default_bucket`, `base_object_path`, `templates_dir`, `chunk_dir`, `pdf_suffix`,
`presigned_ttl_hours` all carry defaults (`settings.py:122-172`), and `minio_public` falls
back component-wise to the internal origin (`settings.py:198-214`). So a local `.env` that
omits `MINIO_PUBLIC_PORT` produces URLs signed for port 9000, and the process starts
successfully. That is the failure mode the brief names: a local environment that comes up
clean and is configured wrongly.

### Verification available today

- `Dockerfile:98` sets a `HEALTHCHECK` on `/openapi.json`. It proves the app imported and
  can serve. It touches neither PostgreSQL nor MinIO.
- The application has **no** health or readiness route, and `app/server.py` registers no
  middleware and no root route.
- `tests/conftest.py:20-24` runs the suite against SQLite in a temp file, and
  `conftest.py:51-66` stubs `Minio._url_open`. A green suite says nothing about either
  dependency.
- The one real storage probe is `ensure_storage_ready()` (`app/core/storage.py:115-134`),
  called from the lifespan at `app/server.py:28`. It is a `bucket_exists` probe: it proves
  reachability and credentials, not that bytes move.

`docs/deployment-guide.md` §5.5 is the real gate — presign, `PUT`, presign, fetch, compare,
delete, from a network that is not the server — and it can only be run on the VPS.

### Blast radius: files shared by both environments

| File | Authoritative for | Decision |
|---|---|---|
| `Dockerfile` | **both** — VPS `build:` and local pre-prod run | Edit. Risk + rollback in tasks. |
| `requirements.txt` | **both** — both stages, VPS runtime | Split. |
| `app/core/settings.py` | **both** — every process | Edit. |
| `.env.example` | **both** — template for each | Edit (documentation only). |
| `infra/schema.sql` | **both** — VPS §2.2, local schema on the core | No edit. |
| `infra/provision/001-create-application-roles.sql` | **both** — VPS §2.1, local role on the core | No edit, reuse with placeholders. |
| `alembic/`, `alembic.ini` | **both** | No edit. |
| `Makefile` | dev only | Edit. |
| `tests/test_deploy_assets.py`, `test_provisioning.py`, `test_skill_agnosticism.py` | read `Dockerfile`, `infra/vps/`, skill prose | No edit; keep green, extend if useful. |
| `infra/vps/docker-compose.yml`, `infra/vps/Caddyfile` | **VPS only** | **Untouched.** |
| `docs/deployment-guide.md` | **VPS only** | **Untouched.** |
| the core project's own compose file and image definition, in the sibling repository | **the shared core, locally and on the VPS** | **Untouched.** This change consumes them. Recorded here because a file that lives in another project is still a file that a careless edit would reach. |
| root `docker-compose.yml`, `bootstrap.sh`, `core/**`, `etl/**` | dev only, all broken/stale | Out of scope. |

### Constraints

Local stack files go under `infra/local/`. Nothing ships a local-only edit into
`infra/vps/`, and nothing edits a declaration owned by another project. Provisioning on the
shared core is additive and confined to this project: it creates a role, a database, a
bucket and credentials, and touches no shared configuration file. No production data locally
in any form. No real credential in any committed file. No Kubernetes, GitOps, canary or
observability vendor. Do not build the image on the target. No staging environment. English
throughout.

## Goals / Non-Goals

**Goals:**

- One documented command brings up everything this project needs from a clean checkout — the
  shared core, this project's own role, database and bucket, and the schema — and a second
  proves it works.
- Local reaches its dependencies the same way the deployment does, so the inner loop is a
  rehearsal rather than a different system.
- Isolation from the other consumers of the shared core is enforced by the database, the
  role and the bucket, and the gate refuses to run against anything that is not this
  project's own.
- The proof is made against the image that ships: not root, no development tooling.
- The gate exercises an authenticated read, a write, and a storage round trip through the
  application's own client, so a missing migration, an exhausted pool or wrong credentials
  fail it.
- Configuration resolves through one code path with no environment-varying default.
- Local and VPS port and hostname values both recorded, never silently aligned.
- No file under `infra/vps/` changes, and no file owned by another project is edited.

**Non-Goals:**

- Any edit to `infra/vps/**`, `docs/deployment-guide.md`, `core/**`, or the core project's
  own declaration in the sibling repository.
- Declaring this project's own PostgreSQL or object store. Decision 1 consumes the shared
  core instead.
- Repairing `bootstrap.sh`, `etl/**`, `packages/specboot/**`, or the remaining stale
  references in `docs/development_guide.md` and `README.md`. Where those documents are
  contradicted by the new bring-up, this change adds the new documented path; correcting the
  rest is a separate task and a separate review.
- Applying the VPS's connection-level isolation locally, which would mean editing a shared
  configuration file. Open question 4 records that as an estate decision.
- Fixing `TICKET-019` (models 94 operations stale against the live database). Local schema
  comes from `infra/schema.sql` plus `alembic upgrade head`, never autogenerate.
- Adding a health or readiness endpoint. The gate does not need one; see decision 9.
- Building the image on the VPS, or transferring an image artifact between hosts.
- A staging environment, or any substitute for one.

## Decisions

### 1. Native service, shared core consumed, built image before release

This design **consumes** the estate's shared PostgreSQL and MinIO locally instead of
declaring private copies. That reverses the first draft of this change, which proposed
containerized dependencies of its own, and the reason is worth stating because it is the
whole argument.

The estate already has a core that several of the developer's own projects use, and the
VPS arrangement this change must not disturb is one role, one database and one bucket per
application on a shared instance. Declaring a second PostgreSQL and a second MinIO locally
would have produced two local topologies and therefore two configuration shapes — the
opposite of what parity asks for — and it would have made the developer's local experience
*less* like the deployed one than doing nothing.

**Isolation is the database, not the instance.** Sharing one PostgreSQL instance while
giving each application its own database and its own least-privilege role is the ordinary
way to share, and it is what the VPS already does. The failure modes that argue against a
shared core — concurrent interference, and one application's migration breaking another's —
come from sharing a *database*, and per-database isolation removes both. The one thing that
must never be shared is the database.

The intended split, decided as follows:

- **Native:** the API process (`venv/bin/uvicorn`) and `pytest`. The inner loop needs a
  sub-second edit-to-response cycle and direct access to the source tree; a bind-mounted
  container with reload adds a layer without adding fidelity.
- **Consumed, not declared:** PostgreSQL and MinIO, reached on the developer's existing
  shared core. This repository declares no database service, no object-store service and no
  data volume. What it declares is its own database, role, bucket and credentials on that
  core — an additive provisioning step, the same one the VPS performs.
- **Built image, locally, before release:** a third run mode. `make stage-local` builds the
  default `runtime` stage of the unmodified `Dockerfile` and runs it against the shared
  core with production-shaped settings. This is the substitute for a staging environment,
  which the constraints exclude.

**What this gives up, stated plainly.** The local environment is no longer
self-contained. A clean checkout cannot produce a working stack without the shared core
being startable from the project that owns it — which is the same out-of-tree dependency
this change set out to remove, in a different form. It is accepted for three reasons: the
topology becomes the deployed one, the provisioning doctrine becomes the one already in
use, and the alternative duplicates a database and an object store per project. The
mitigation is that the dependency becomes an orchestrated, named, checked step rather than
tribal knowledge: `make setup-local` starts the core, provisions this project's role,
database and bucket, and migrates — and fails with a readable message naming the missing
prerequisite if the core is not there.

Alternative rejected: containerized private dependencies of this project's own. It is
sound on its own terms and was the previous draft of this decision. It was dropped because
it invents a second topology, and because a private local object store would have been the
component whose signing-origin configuration is easiest to get subtly wrong and least
likely to be noticed.

### 2. Local ports are the shared core's own, and both environments are recorded

Nothing is published locally any more, because this repository publishes nothing. The API
is the only service it declares, and the core's own published ports are reused as they are:

| Setting | Local | VPS | Why |
|---|---|---|---|
| API host port | `127.0.0.1:8000` | `127.0.0.1:8000` | Same. Only Caddy reaches it on the VPS. |
| PostgreSQL host port (native API) | the core's published loopback port | none published (dial the container name in-network) | The core already publishes one for host-side callers; reusing it is what makes the developer's machine consistent with itself. |
| PostgreSQL in container mode | the core's container name and `5432` | the container name and `5432` | **Same as the VPS.** |
| MinIO API host port (native API) | the core's published loopback port | none published (dial the container name in-network) | Same reason as PostgreSQL. |
| MinIO in container mode | the core's container name and `9000` | the container name and `9000` | **Same as the VPS.** |
| MinIO console host port | the core's published console port | not published | Local convenience, inherited from the core. |
| Public media origin | loopback, plain HTTP, on the core's published API port | `media.example.com:443` TLS | No TLS edge locally. |

The VPS values are quoted from `infra/vps/docker-compose.yml:52-53`, `:67-68`, `:86-95`.
They are recorded as read; this change does not touch them.

The concrete local values are **not written into this design as numbers**. They are the
core's, they are recorded by whoever owns the core's declaration, and a copy of them here
would be the second place they could drift — which is precisely the failure
`core/compose.yml` already demonstrates. The task that writes `.env.example` copies them
from the owning declaration and cites where each came from.

**What the engine settles, and what it forbids.** `docker ps -a` shows the core's
containers exist on the developer's host, currently stopped, and each carries the compose
project, working directory and config files that created it. So:

- the local compose file declares **one network of its own** and creates it. Both the API
  and the migration job attach to it, and the core's already-running containers are
  connected to it by the bring-up command;
- the local compose file declares **no** volume, and mounts no shared one. There is no
  local data to protect, because there is no local data;
- it declares its own compose project name, so `docker compose down` from this repository
  can never match a container this repository did not create;
- it reuses **no** container name from the core. A local container that borrowed a shared
  name would resolve ambiguously depending on which network won the lookup, and could be
  stopped by someone else's cleanup;
- it publishes only the API, on `127.0.0.1`;
- it issues **no** `stop`, `restart`, `rm` or `start` against a core container. Connecting a
  container to a network is the whole of what it does to one.

**Why one local network rather than joining the core's — the core's shape is a free choice.**
A shared core can be composed four ways, and all four are legitimate:

| # | Database | Object store | Networks |
|---|---|---|---|
| 1 | one server | one server | **one** — both in a single compose |
| 2 | one per app/web/unit | one per app/web/unit | one per unit |
| 3 | one grouping all apps | one for all apps | one, *if* both are declared together |
| 4 | one for all apps | one grouping all apps | one, *if* both are declared together |

Only (1) makes a single network inevitable. (2)–(4) produce as many networks as there are
groupings, so the count is a property of the grouping, not a fact about the dependency.

**Arrangement (1) is the deployed one.** On the VPS both core containers are created by a
single compose file in a folder named `core/`.

That folder layout is **estate knowledge, not something this repository can show you**, and
the two halves of the claim have different evidence, so they are recorded separately:

- **Verifiable here.** `infra/vps/docker-compose.yml:205-209` requires one network with both
  dependencies attached, and `docs/deployment-guide.md:46-47` connects `postgres-gci` and
  `minio-acme` to that same network. So the *consequence* — one network carrying both — is
  established by this repository.
- **Asserted by the owner.** That both containers come from one compose file, in a directory
  named `core/`, is stated by the project's owner and is recorded only in the OpenSpec change
  directory. **There is no `core/` folder in this repository**, and anyone looking for one will
  not find it. Do not go looking to confirm the arrangement here; read it from the estate.

The local mirror disagrees with the deployed layout, and the disagreement is not a second
design. The mirror composes the database in `~/Documents/GoogleCloudProjects/core/compose.yml`
and the object store in
`~/Documents/GoogleCloudProjects/gci-companies/gci-empresa-a/assync/docker-compose.yml`, two
directories in two compose files, so this machine shows two networks where the VPS shows one.
Note the collision of names, because it is a trap: the mirror's `core/` holds *only* the
database, and it is not the same directory as the VPS's `core/`, which would hold both. Same
folder name, different content, different machine. The mirror's *sharing ratio* — one database
grouped across several applications, one object store per application — is arrangement (3)'s
ratio and is deliberate; its folder boundary is incidental.

So the deployed arrangement is fixed, and the local one matches it exactly: one network,
both dependencies attached, reached by container name, with in-container ports. That is the
parity this change buys, and it is bought *without* a network name, because of the four-way
choice. **A consumer has no network name it may depend on.** Depending on
`infrastructure-companies_gci-db-network` or `assync_as-sync-acme-network` would encode a
mirror directory's incidental boundary as a requirement of this repository: rename it over
there and this stack breaks with a DNS error that its own healthcheck passes straight
through. The name is a decision the core's owners are free to take back at any time — that
is what "four arrangements" means — so depending on it is depending on a choice, not on an
interface.

**Isolation is unaffected by which arrangement is chosen.** Sharing a *server* is ordinary
and is what the estate does; sharing a *database* is never acceptable. Read (3) and (4) as
"one server for everything", every one of the four keeps this change's boundary intact: its
own database, its own least-privilege role, its own bucket, its own credentials. The
arrangement decides how many networks and servers exist. It does not decide who may read
whose rows.

**Redundancy multiplies the names, which is why the rule is worth having now.** No
second network or failover path per application exists today. When one is added, a consumer
that had hard-coded a single provider network name has to be revisited to learn about a
network it was told was the only one. A consumer that owns its own network has a place to
put the second one without the core changing at all. Retrofitting that later means auditing
every consumer; adopting it now costs one network per application. Recorded as a follow-up
in `tasks.md` §17.15 rather than solved here.

**The attachment is a cache, not the durable copy — and only the provider can make it
durable.** The connect below puts state *inside* the core's container, so the next recreate
performed by the core's own project erases it: no log line, no error, and the API then fails
on its first request while its healthcheck passes. Two remedies exist and only one of them is
available here. The durable one is provider-side: each application's network declared
`external: true` on the core's own service, so the attachment is declarative and a recreate
reproduces it. That is a change to the core's `core/compose.yml`, which this repository does
not own and must not edit — recorded as a raise in `tasks.md` §17.16.

So the local arrangement is necessarily the weaker one, and it is weaker *by constraint, not
by choice*: the provider's file is off limits, which is precisely why the connect is
idempotent and re-run at every bring-up, and why it reports which attachments it made. When
the estate declares the network, that idempotent connect becomes a harmless no-op rather than
the only line of defence — and it must remain in place regardless, because a provider who has
not declared a consumer's network yet is the ordinary case.

**The pattern that remains, and its cost.** The core's containers are started by their
owner. A project then declares a network of its own and the bring-up command connects the
running containers to it, after confirming they are running. Reachability is by container
name across that network. This costs one thing and it is not optional to design around:
`docker network connect` state lives *inside* the container, so **a recreated container
loses the attachment silently**. Two consequences are therefore requirements rather than
polish — the connection must be idempotent and re-runnable, and the teardown must detach
before the project is removed, because `docker compose down` cannot remove a network that
still holds an attachment to a container it does not own.

**This pattern is the estate's, not an invention here.** The owning project documents it at
`provider-portal/README.md` (Infrastructure §1), per application:

```bash
docker network create my-<app>-network
docker network connect my-<app>-network postgres-gci
docker network connect my-<app>-network minio-acme
```

One dedicated network per application, created once **outside** any compose file, with the two
shared core containers attached to it. So the estate already answers the question this section
was reasoning toward, and the local decision inherits the answer instead of inventing a second
topology next to it.

Applied to this project, that has a consequence which is deliberately **not** acted on here. On
the VPS, app-tickets' network would be `my-tickets-network` — the same shape as
`my-dopamine-network`, a distinct network, created once by the deployment procedure and declared
`external: true` by the app's compose. Renaming the deployed network changes a contract that six
artifacts and one live procedure depend on, and `infra/vps/docker-compose.yml` is no-touch in this
change for that reason. It is recorded as its own change in `tasks.md` §17.11–17.13, together with
the failure mode the deployed arrangement actually exhibits: a rename that updates the `name:` value
but leaves the network key and its five internal references alone still validates, while placing
Caddy, the API and the migration job on another tenant's bridge.

Locally the same pattern runs with a local instance of the name, `app-tickets-local-net`, created and
destroyed by this stack rather than pre-created by an operator. The difference is not
inconsistency, it is that there is no deployed network to join on a laptop and no operator to run the
create step — so the ownership sits with `make setup-local`, which is also what makes it idempotent and
re-runnable after a core container is recreated. The caveat the estate's procedure names — a new app
must not bind an internal port already bound inside the same container — is satisfied by
construction: this stack publishes only `8000:8000` and binds neither the PostgreSQL nor the MinIO port
inside any core container.

**Alternative rejected:** connecting to each of the core's own networks as `external`. It
avoids touching the core's containers at all, and on a core owned by someone else that is
the stronger position. It was rejected here because it couples this repository to another
repository's network naming, and because it leaves the two dependencies on two networks,
which is a topology production does not use.

### 3. Configuration: one code path, no environment-varying defaults, one env file name

`app/core/settings.py` stays the single resolution path. The change is to remove defaults
from every setting whose value can differ per environment:

- Required already, unchanged: `TZ_COMPANY`, `COUNTRY`, `CLIENT_*`, `CONTRACTOR_*`,
  `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`,
  `MINIO_SECRET_KEY`, `EXT_BY_TYPE`, `ALLOWED_TYPES`, `JWT_SECRET`, `JWT_ALGORITHM`,
  `JWT_EXPIRE_MINUTES`.
- Defaults to remove: `pg_port`, `minio_port`, `minio_secure`, `minio_region`,
  `minio_default_bucket`, `base_object_path`, `presigned_ttl_hours`, `pdf_suffix`,
  `templates_dir`, `chunk_dir`.
- Fallback to remove: `minio_public`'s component-wise fallback (`settings.py:198-214`).
  `MINIO_PUBLIC_ENDPOINT`, `_PORT` and `_SECURE` become required. A missing public origin
  must fail, not silently sign with the internal host — that is exactly the defect
  `split-minio-internal-and-public-endpoints` resolved, and reinstating a fallback undoes it.

`presigned_ttl_hours` keeps its `AliasChoices("PRESIGNED_TTL_HOURS", "PRESIGNED_TTL")`
chain so an existing `.env` is honoured; only the default goes.

**One env file name everywhere.** Local uses `.env`, the same name the VPS uses
(`infra/vps/docker-compose.yml:61`). Only the values differ. `.env.example` gains a local
section stating which keys differ and why; it is a template, and the deployed `.env` is a
copy, so no deployed value changes.

**Alternative rejected:** a `LOCAL_`-prefixed key namespace, or a second settings class for
local. Both add a branch on environment, which is the thing to avoid.

### 4. Reaching PostgreSQL and MinIO: name resolution per run mode

Two run modes, two correct answers, and they must not be confused. The good news is that
both now match the deployed arrangement exactly, so there is one set of rules rather than a
local variant of them.

**Native (API on the host):** the core's published loopback address and port — the values
recorded in `.env` by the setup step, copied from the core's own declaration. The
in-container ports are not reachable from the host; the published ones are.

**Container (the built image, or the `migrate` job):** the core's container names and their
in-container ports, resolved across this project's own network, which the bring-up command
has attached them to. That is byte-for-byte the same shape as `infra/vps/docker-compose.yml:67-95`,
which is the point of the decision — same dial-by-container-name, same in-container ports,
only the network's name and who created it differ.

The trap, stated at each override: **inside a container `127.0.0.1` is the container.** A
`MINIO_ENDPOINT=127.0.0.1` inherited into the image points every upload and the startup
bucket probe at nothing, and the container still starts and looks healthy. This is the
documented failure in `infra/vps/docker-compose.yml:71-80` and the subject of
`docs/post-mortems/2026-09-29-minio-endpoint-lease-outage.md`. The local compose file
overrides the host values with the core's container names, and says why at the override — it
never edits `infra/vps/`.

Because the values now come from the core's declaration rather than from a list written
here, `.env.example` must not carry them as literals without saying where each was read
from. A value copied without its provenance is a value that will silently outlive the thing
it was copied from.

Both run modes also need `pool_pre_ping` behaviour, which `app/core/database.py:8` already
sets; nothing to change.

### 5. Local object store: no public origin, plain HTTP on loopback

Locally the public origin is the loopback address and port the core already publishes for
its API, with `MINIO_PUBLIC_SECURE=false`. There is no Caddy to terminate TLS, and the
signed URL must be fetchable from the host — which is what makes the gate's round trip
possible.

This is not an invention. The engine shows the core's own MinIO already configured with a
public endpoint of `127.0.0.1`, the published API port, and `secure=false`, so the local
shape is the core's existing convention rather than a local special case.

The VPS counterpart is `media.example.com:443` TLS
(`infra/vps/docker-compose.yml:93-95`). The values differ and are recorded side by side.
Note the direction of the difference: on the VPS the public origin is a domain the mobile
app resolves; locally it is loopback, which no remote client could resolve. That asymmetry
is a limit of the local check and is stated as one.

One consequence of sharing the object store, worth stating because it is easy to get wrong:
**the signing origin is a per-application setting, not a per-server one.** The server does
not know what public origin its presigned URLs should carry; the application signs with its
own configured public origin. So several applications can share one object store and each
sign for its own origin, which is why nothing about sharing forces a shared public origin
here.

### 6. Caddy is excluded, and here is what replaces it

Caddy's whole job is terminating TLS for a public origin and proxying two hosts. Locally
there is no public origin and no certificate to issue. Running it locally would test ACME,
hairpin NAT and a domain name that resolve to nothing — the failure mode
`infra/vps/docker-compose.yml:20-26` and `docs/post-mortems/…lease-outage.md` describe.

Excluded, because it tests something that does not exist locally and its absence breaks no
local requirement.

What verifies the media path instead, in the gate: write an object through the
application's own upload path, presign a read, `GET` it back, compare bytes, assert the
signed host is `MINIO_PUBLIC_ENDPOINT` and not `MINIO_ENDPOINT`, then delete. That is the
same substance as `docs/deployment-guide.md` §5.5, minus TLS.

**Left unverified locally, stated explicitly:** TLS termination and certificate renewal;
public DNS resolution; edge `Host`-header preservation, which is what makes SigV4 validate
in production; the media host's reachability from the internet. §5.5 and §5.4 on the VPS
cover these. A local Caddy with a self-signed certificate would not cover them either — it
would cover a different, non-production path.

### 7. Seeding: deterministic, structurally faithful, no production data, no committed credential

`infra/local/seed.sql` — schema-faithful rows only: units of measure with a resolvable
self-reference, one market, one equipment, one labsdl, one technician, one service account.
Synthetic names (`Local Market A`, `EQ-LOCAL-0001`), no real persons, no real identifiers,
no extract of any kind. `infra/schema.sql:8` records the schema is a live `pg_dump`, so
copying rows out of it was a real risk; none are copied.

Loaded through `etl/seed_db.sh` with a local data folder, not a hand-written `psql` call.
That loader already enforces what a naive seed would not: `ON_ERROR_STOP=1`, the business-
table allowlist, the numeric-fidelity gate (`seed_db.sh:333-400`), the parent-before-child
loop for the self-referencing `uom` table, and the post-load orphan check (`:416-443`).
Reusing it means the local path inherits the same guarantees as the loader the project
already trusts. Its `mktemp` template hardcodes `/tmp/opencode` (`:255-256`) — the local
bring-up creates that directory or the seed fails, and that is recorded rather than papered
over.

Idempotence comes from the loader itself: it skips a table that already holds rows
(`:258-410`), so a second run is a no-op.

**No committed credential.** The seed account's password is read from the developer's
git-ignored `.env`; the committed example carries the generation instruction
(`openssl rand -base64 32`), not a value. `.gitignore:1` already ignores `.env`. A test
asserts no password-shaped literal exists in any committed file.

### 8. File-watcher scope

`Makefile:111` runs `$(VENV)/bin/uvicorn app.main:app --reload` with no `--reload-dir`, so
watchpack watches the project root — including `venv/`, which holds one directory per
installed package. A `pip install` therefore multiplies the watch count, and the resulting
`ENOSPC`/watch-limit failure surfaces on the *next* reload, minutes later, with no relation
to its cause. That is the failure the brief describes.

Fix: `--reload-dir app`, plus explicit excludes for `venv`, `.pytest_cache` and `.coverage`.
`README.md:35` and `docs/development_guide.md:34` already use `--reload-dir app`; the
Makefile is the outlier, so this makes the documented paths agree.

Editor-side watching is not configured — `.vscode/` holds only `shortcuts.json`, an empty
array — so no `files.watcherExclude` entry exists to fix. Adding one is cheap insurance and
is in scope.

### 9. The gate: why no health or readiness endpoint is added

The application has neither. The three kinds of check are not interchangeable:

- **Liveness** (`/openapi.json`, the existing `HEALTHCHECK`) proves the process imported and
  serves. It touches no dependency. It is necessary and insufficient.
- **Readiness**, if added as `GET /health/ready` that only confirms the event loop is
  accepting, would be the same check under a new name.
- **A check that exercises the application's own path** — through `get_db`, through
  `get_minio_client`, through a real token — is the only kind that catches an exhausted
  connection pool, a missing migration, or wrong credentials. Those three are exactly the
  failures that leave a container "healthy".

So: do not add an endpoint. The gate drives the real API. `GET /auth/me` is the
authenticated read — cheapest in the app, one primary-key lookup, plus it already runs the
blacklist query and the user fetch, so a wrong JWT secret or a missing `token_blacklist`
table fails it. The write is `POST /tickets` with a deterministic description, deleted
afterwards so the gate leaves the database as it found it. The storage round trip uses the
`/uploads/init` → `/uploads/chunk` → `/uploads/complete` path, because that is the code
path a phone actually takes and it goes through `app/core/storage.py`.

### 10. The shipped image must be non-root and free of development tooling

This is a change to what ships, and the acceptance criteria demand it.

Today the `runtime` stage has **no `USER` instruction** — the container runs as root — and
installs `gcc`, `libpq-dev`, and, through `requirements.txt`, `pytest`, `pytest-cov`,
`pytest-asyncio`, `factory_boy`, `httpx` and `pandas` (which nothing in `app/` imports;
it is used only by `etl/transform_csv.py`). `.dockerignore` excludes `tests/`, so the test
files are absent while the test tooling is present.

Change: `requirements.txt` becomes runtime-only; a new `requirements-dev.txt` holds the
test and ETL packages; `make setup` installs both, both Dockerfile stages install only the
runtime file; the `runtime` stage drops `gcc`/`libpq-dev` after the build step and declares
a non-root `USER`. The `migrate` stage is unaffected in substance — it needs `alembic`,
`psycopg2`, and `app.core.settings` to import `app.models`, all runtime.

Risks, both real:

- `gcc`/`libpq-dev` are build dependencies. Removing them from the final image is correct
  only if they are removed *after* `pip install`, in the same stage. The current single
  stage installs them in the same `RUN` as the OS packages. The change must either reorder
  or add a final layer that removes them.
- A non-root `USER` changes file ownership of anything the process writes. `CHUNK_DIR` is
  `/tmp/upload_chunks`; it must be created and owned by the runtime user, or chunked
  uploads fail with a permission error that looks like a storage outage.

Rollback for both: revert the `USER` line and restore the combined requirements file.
Neither rollback touches the VPS compose file.

### 11. Which PostgreSQL image locally: the core's, so this decision disappears

Under the previous draft this repository declared its own PostgreSQL service and therefore
had to decide which image to build. Consuming the core removes the decision, which is worth
recording rather than silently dropping.

`infra/schema.sql:113` executes `CREATE EXTENSION IF NOT EXISTS pg_uuidv7`, and
`docs/deployment-guide.md:39-40` records that the shared image is a custom build
(verified PostgreSQL 16.13, `pg_uuidv7` 1.7) that stock `postgres:16` does not satisfy.
`TICKET-007` notes nothing in the repository records how to reproduce it — except
`core/postgres-gci/Dockerfile`, which is exactly `FROM postgres:16` plus
`postgresql-16-pg-uuidv7` and which no document cites. The engine confirms the image was
built from that definition, and that the running container's image is a project-scoped
build rather than the stock tag.

So the extension requirement is satisfied by the core, and this change neither rebuilds nor
pins a PostgreSQL image. Two consequences:

- `infra/schema.sql` and `alembic upgrade head` run against the core unchanged. No local
  bootstrap DDL is needed, so there is no second copy of the schema to drift.
- If a future developer's core *lacks* `pg_uuidv7`, that is a finding against the core's
  image, not a local problem to work around. The setup step's error must say so rather than
  suggesting a local image build.

Version parity is now the core's parity with the VPS, which is an estate question rather
than this project's. Open question 2 records that no MinIO version is written down anywhere
— the engine confirms the running image is an unpinned `:latest` tag — so parity cannot even
be asserted yet.

### 12. No cross-host image build

Local builds and runs the image on the same host. `infra/vps/docker-compose.yml:42-45`
builds on the VPS, which is how it works today and this change leaves it alone. Building an
artifact on one host and running it on another is a separate change with its own decision —
recorded as a dependency in the design's open questions, not answered here.

## Risks / Trade-offs

**[The local environment now depends on a project outside this repository]**
→ This is the cost of the central decision, and it is not eliminated, only made visible.
`make setup-local` orchestrates the whole sequence — start the core, wait for it, provision
this project's role and database and bucket, migrate — so the dependency is one command
instead of folklore. If the core is absent the command fails with a message naming what is
missing and who owns it, rather than with a connection error from the application. The
alternative, a private local core, was rejected in decision 1; it is recorded here so the
trade is visible to a reviewer rather than settled by assertion.

**[Provisioning on the shared core is a mutation of state other projects can observe]**
→ Local provisioning is restricted to what is **additive and confined to this project**: a
role, a database, a bucket, a user, and this project's own credentials. It deliberately does
**not** edit any shared file. In particular it does not edit `pg_hba.conf` and does not
restart the core's containers, because both would change behaviour for every other consumer
of an instance this project does not own. The stricter connection-level isolation used on the
VPS is a deployment-time concern and is not applied locally; open question 4 asks whether the
estate wants local provisioning to be self-service at all, or owner-run.

**[The gate mutates a shared instance]**
→ The gate's write is confined to this project's own database and its own bucket, and it
deletes what it creates. Before it runs, it asserts that the resolved connection string names
this project's own database and that the object-store bucket is this project's own; if
either does not, it aborts without writing. The failure mode being prevented is the gate
creating a row in a database another project is using.

**[A shared core and a shared object store mean a developer's local state is not
disposable]**
→ Accepted. A developer who wants a discarded environment drops *this project's* database
and bucket and re-provisions; it does not disturb the core or any other project. This is
strictly less destructive than the previous draft, where each project had its own volumes to
throw away.

**[Local and VPS now look alike, so a local-only defect becomes harder to see]**
→ The gate's printed block states what it does not exercise: TLS termination, public DNS,
edge `Host`-header preservation, the VPS network, and its scheduling. Those remain covered
only by `docs/deployment-guide.md` §5.4 and §5.5 on the VPS. Greater similarity is the goal,
but it must not be reported as coverage.

**[Removing `MINIO_PUBLIC_*`'s fallback breaks an existing `.env` that omits them]**
→ This is intentional and is the point: the omission must fail rather than sign URLs with
the internal host. The rollout task states the exact error and the fix. The VPS `.env`
already sets all three (`infra/vps/docker-compose.yml:93-95`), so no deployed value changes.
`tests/test_minio_endpoints.py:159,207` assert the fallback and must be updated to assert
the failure instead — a deliberate behaviour change, not a test to silence.

**[Removing defaults breaks a `.env` that omits any of them]**
→ Each removal is listed in `proposal.md` and `design.md`. The failure is loud, at import,
naming the missing key — the intended outcome. `tests/test_env_collection_settings.py`
spawns subprocesses importing `app.core.settings`; it must be extended to cover the newly
required keys rather than left to fail opaquely.

**[Splitting `requirements.txt` breaks the `migrate` stage if a runtime package is
misclassified]**
→ `alembic` and `psycopg2` stay runtime (the migration image cannot run without them).
The existing `tests/test_deploy_assets.py` already asserts the `migrate` stage carries the
revision scripts; the local pre-prod run exercises the migration end to end, which is a
stronger check than the static one.

**[A non-root `USER` breaks chunked uploads through a permission error that reads as a
storage outage]**
→ `CHUNK_DIR` is created and chowned by the local compose definition. The gate's
`/uploads/*` round trip exercises exactly this path, so the failure cannot pass silently.

**[The gate is weaker than the VPS §5.5 gate]**
→ Stated in three places: the spec, the design, and the gate's own printed output, which
prints the limits as part of the pasteable block. A release note that pastes the block
therefore carries its own caveats.

**[`etl/seed_db.sh` requires an elevated role, and the local runtime role is
least-privilege]**
→ Local seed runs as the database owner, exactly as `docs/deployment-guide.md` §2.3
describes for the VPS. The runtime role stays low-privilege; two credentials exist locally
for the same reason they exist on the VPS. `tests/test_seed_loader.py` covers the loader;
the local invocation is covered by a new assertion.

**[Stale prose in `README.md` and `docs/development_guide.md` keeps misleading
developers]**
→ Acknowledged and deliberately out of scope, with one exception. `README.md` and
`docs/development_guide.md` both instruct the developer to `cd` into another project to
start PostgreSQL and MinIO. Under the previous draft that instruction was wrong and had to
be corrected. Under this design it is *nearly* right — the core genuinely is started from
there — so it becomes a documentation obligation rather than an optional cleanup: the new
section states the orchestrated command, and task 11.3 corrects the stale parts that remain
stale (a service the compose never declared, a host address the README itself calls wrong
for this machine, a global install where the Makefile uses a virtualenv).

## Migration Plan

No deployment migration. This change alters the image that ships and the configuration
contract; it does not alter `infra/vps/` or the schema.

Rollout order, because the settings change is the one that can abort a running VPS process:

1. Add `infra/local/**`, the Makefile targets, the local env section, and the gate. Nothing
   here affects a running process.
2. Harden `Dockerfile` and split the requirements files. Rebuild locally, run
   `make gate-local`. The image is not deployed by this step.
3. Land the `settings.py` default removals **together with** the `.env.example` update, and
   verify the VPS `.env` already sets every newly required key before merging. If it does
   not, the deploy procedure adds the keys first; that is an operator step, stated in the
   task.
4. Update `tests/test_minio_endpoints.py` fallback assertions to failure assertions in the
   same commit as step 3, so the suite never disagrees with the code.

Rollback, per step:

- Steps 1, 2, 4: revert the commit. No deployed state changed.
- Step 3: revert `settings.py` and the test assertions. Existing `.env` files keep working
  either way, because adding a value is backward-compatible and removing a default only
  ever made a previously-silent omission loud.
- `Dockerfile` rollback: restore the `USER` line and the combined requirements file. The
  image rebuilds to the previous behaviour.

**One asymmetry, stated because it is the only place this change writes outside its own
repository.** Reverting the code does not revert the local provisioning: this project's role,
database and bucket remain on the shared core, exactly as they remain on the VPS. That is
correct — they are this project's, not the change's — but it means a rollback must never
drop them as a cleanup step. The only supported removal is a separate, explicit act that
targets this project's database, role and bucket by name and nothing else. Because those
objects live on an instance other projects share, that act is irreversible for anything else
that has come to depend on them, which is the reason it is not folded into a rollback.

## Open Questions

Listed and not resolved here, per the brief. They are recorded so the implementer does not
quietly pick one.

1. **Does local development need Caddy, or is it production-only?** Decision 6 excludes it
   and names the verification that replaces it, on the grounds that Caddy's only local role
   would be terminating TLS for an origin that does not exist. If the answer is that local
   development *does* need Caddy — for example to rehearse `Host`-header preservation before
   a SigV4 change — that changes decision 6 and the gate's third check.
2. **Must the shared core run the same PostgreSQL and MinIO versions as the VPS, or is
   approximate parity acceptable?** This was a local question under the previous draft and is
   now an estate one, because the core is shared. PostgreSQL 16 with `pg_uuidv7` is satisfied
   by the core's image; minor-version parity and MinIO parity cannot be asserted at all,
   because no MinIO version is recorded anywhere and the engine shows the running image is an
   unpinned `:latest` tag.
3. **Should the local and VPS environments share one example env file or two?** This design
   uses one file name and one key namespace, with a documented local section, so the code
   has a single resolution path. Two example files, with disjoint key sets, would make the
   per-environment value table harder to read and easier to let drift; one file invites
   editing the VPS guidance while fixing a local problem.
4. **Should local provisioning on the shared core be self-service, or owner-run?** This
   design lets a developer create their own role, database and bucket from this repository's
   setup command, because that is additive and confined to this project. The stricter option
   is that the core's owner runs provisioning and this project only connects. The trade is
   onboarding speed against who is authorised to add state to a shared instance, and it is a
   question about the estate, not about this repository. It also decides whether the
   connection-level isolation used on the VPS should ever be applied locally — which would
   require editing a shared configuration file and restarting a shared container.

Not resolvable from the tree, recorded for the operator rather than answered:

- **Who starts the core, and from where.** The setup command depends on the core being
  startable from the project that owns it. If that project moves, or its path is not stable,
  this repository's setup command breaks. Making the core's bring-up an estate-level
  command rather than a per-project one would remove the coupling, and is the single most
  valuable follow-up this design produces.
- `TICKET-019`: models are 94 operations stale against the live database, so
  `alembic autogenerate` would emit a destructive revision. Local schema therefore comes
  from `infra/schema.sql` plus `alembic upgrade head`. Until it is fixed, local migrations
  can never validate that the models match the schema.
- `TICKET-018`: 5 tables exist in the live database with no model. Local will carry them
  (they are in `infra/schema.sql`) with no code touching them.
- Building an image on the target host and transferring the artifact is a separate change
  with its own decision.