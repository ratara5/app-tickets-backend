# TK MGM API BACKEND

## INFRASTRUCTURE

**This project does not provision its own database or object storage. It
attaches to shared infrastructure.**

PostgreSQL and MinIO already run on this host and are shared with other
applications, websites and projects. Nothing in this repository starts, stops,
recreates or reconfigures them. What this project adds to that estate is its
own, and only its own:

- its own **database** on the Postgres container that is already running — not
  a new database server;
- its own **role** inside that database, holding DML only, owning nothing — not
  an administrator credential;
- its own **bucket** and bucket-scoped service account on the MinIO instance
  that is already running — not a new object store.

This infrastructure is previously existing. Treat every container you did not
start as someone else's, and every change you make to it as additive: a network
you join, a database you create, a bucket you create — never a container you
replace.

### Two paths — pick the one that matches your situation

**Path 1 — the shared containers are already running** (this project's default
assumption, and the only path this repository implements today). PostgreSQL and
MinIO exist, belong to other projects, and are reachable by container name.
You attach: create this project's database and role inside the existing
Postgres container, create this project's bucket inside the existing MinIO
instance, join the shared network, then run this project's own stack.

**Path 2 — the shared containers are not running yet.** *(Detailed content for
this path is still to be supplied by the owner of this repository; until it is,
follow Path 1 — this repository does not start the shared containers itself,
because they belong to another project, which starts them.)*

> Details on the isolated database and the isolated bucket — exact names,
> credentials and the verification for each — will be added here when they are
> provided.

### The four files

| File | What it is | Plane | Runs |
|---|---|---|---|
| [`infra/schema.sql`](infra/schema.sql) | the schema of record — a `pg_dump --schema-only` snapshot of the live database (23 tables) | 2 — tables | once, into an empty database, by an administrator |
| [`infra/provision/001-create-application-roles.sql`](infra/provision/001-create-application-roles.sql) | the single least-privilege application role and its grants | 1 — admin, one-time | once, **after** the schema is loaded, by an administrator |
| [`infra/vps/docker-compose.yml`](infra/vps/docker-compose.yml) | the stack this project owns: API, one-shot migrate job, Caddy edge, on the shared `infra-net` | 3 — deploy | every deploy |
| [`infra/vps/Caddyfile`](infra/vps/Caddyfile) | TLS and reverse proxy for `API_DOMAIN` and `MEDIA_DOMAIN`, by container name | 3 — edge | read by Caddy on every start |

The two SQL files are hand-run, reviewable artifacts. They are **never**
executed by `docker compose up`, by the application container, by a migration
job, or by the data loader: a shared instance's databases and credentials must
not be created by an arbitrary application's compose file. The application does
not hold the credentials to create a database, and it should not.

The two `infra/vps/` files are this project's half of the deployment. They
declare only what this project owns — `caddy`, `api-acme` and the one-shot
`migrate` job — and attach to containers and networks created elsewhere.

### Using all four together

Steps 0–5 are one-time, hand-run administrator actions. Step 6 happens once and
is then edited by hand. Step 7 is the deploy, and it repeats.

```bash
# 0. ONE TIME — put the shared containers on the shared network. Compose cannot
#    attach a container it does not own, so this step is manual and additive:
#    the other tenants' endpoints and published ports are untouched.
docker network inspect infra-net --format '{{range .Containers}}{{.Name}} {{end}}'
docker network connect infra-net postgres-gci
docker network connect infra-net minio-acme

# 1. ONE TIME — this project's own database, created EMPTY on the container
#    that is already running. No new database server.
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c 'CREATE DATABASE db_gestiket_acme;'

# 2. ONE TIME — build the schema from infra/schema.sql, before any grant is
#    written: the grants apply to existing objects, and ALTER DEFAULT
#    PRIVILEGES only covers the objects created after it runs.
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres -d db_gestiket_acme \
  < infra/schema.sql

# 3. ONE TIME — the least-privilege role, from
#    infra/provision/001-create-application-roles.sql. Substitute every
#    <placeholder> first; never leave a literal in place.
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  < infra/provision/001-create-application-roles.sql

# 4. ONE TIME — the pg_hba.conf rule: the allow line, then the deny line after
#    it, both inserted ABOVE the instance's broader rules — never below them,
#    because pg_hba.conf is first-match and a rule at the bottom is dead.
#    Reload, never restart. See docs/deployment-guide.md §2.1.1, and verify the
#    deny line actually bites from a different host before trusting it.

# 5. ONE TIME — the bucket, the bucket-scoped user, the policy and the service
#    account on the MinIO instance that is already running. Documented in
#    docs/deployment-guide.md §3. (Details pending.)

# 6. ONCE, THEN EDIT — configuration: the two hostnames, the ACME address, the
#    role's credentials and the bucket's service-account keys. The copy is a
#    first-run action only: never re-run it over a filled-in .env.
cp .env.example .env

# 7. EVERY DEPLOY — the stack this project owns. Caddy reads
#    infra/vps/Caddyfile, obtains the certificates on first start, and proxies
#    both hosts by container name.
docker compose -f infra/vps/docker-compose.yml config >/dev/null
docker compose -f infra/vps/docker-compose.yml up -d --build
```

The full sequence, its gates, and its rollback are in
[`docs/deployment-guide.md`](docs/deployment-guide.md); the method behind it is
in `.opencode/skills/deploying-backend-vps/SKILL.md`.

### Provisioning a database and roles on a shared PostgreSQL instance

These files are **Plane 1 (admin, one-time) operations**. They are run by hand
in an administrator's `psql` session. They are never executed by
`docker compose up`, by the application container, by a migration job, or by the
data loader.

A shared instance's databases and credentials must not be created by an
arbitrary application's compose file. The application does not hold the
credentials to create a database, and it should not.

#### The order that matters

Database creation, schema load, role grants, and the network rule are four
separate acts, in this order:

1. **Create the database, empty**, as an administrator. Not owned by the
   application role. No schema yet.
2. **Load the schema of record** — `infra/schema.sql`, a dump of the live
   database. This creates every table, constraint, index, and extension.
3. **Create the roles and grant privileges** — `001-create-application-roles.sql`.
4. **Add the `pg_hba.conf` rule** for the role, and reload.

Grants come *after* the schema because the grants at the end of the SQL file
apply to existing objects, and `ALTER DEFAULT PRIVILEGES` only covers objects
created after it runs. Doing it the other way round leaves every current table
ungranted.

The `pg_hba.conf` rule comes last because it can be verified independently, and
because a role with no privileges is harmless until it is reachable.

#### One role, not two

| Role            | Holds                                | Used for            |
|-----------------|--------------------------------------|---------------------|
| `<runtime>_app` | DML on the 17 modelled tables (below) | the running service |
| — *(administrator)* | ownership of the schema        | migrations         |

There is no migration role. That is a correction, not an omission, and it is
worth understanding before changing it back.

An earlier version of this file created a second role holding `CREATE` on the
schema, so that DDL would be separated from DML. The intent was to answer "what
damage can the running service do?" — but the mechanism did not do what it
looked like it did. In PostgreSQL, `GRANT CREATE ON SCHEMA` permits creating
*new* objects; `ALTER` and `DROP` on existing ones require **ownership**, and
ownership is never granted to an application role here. So the migration role
could create an empty table and could not alter a real one. It could not do the
job it existed for, and the test that appeared to prove otherwise had only
exercised a table that role had just created itself.

The two ways to make a real DDL role work are both worse than not having one:

- **Transfer ownership of every table to the migration role.** Now the
  credential that exists to reshape the schema owns the data, and the
  "ownership is never transferred" rule — the load-bearing part of this file —
  is gone.
- **Grant the migration role to the runtime role.** Then a compromised service
  credential has every capability the migration role has, which is the thing the
  split was supposed to prevent.

So schema change stays with the administrator who owns the schema, and the
running service has no part in it. Migrations are run by a human, as the owner,
the same way the schema of record is loaded in the first place. This also matches
what the sibling project converged on, and it is the simpler design.

Neither capability attribute is granted: the role is `NOSUPERUSER`,
`NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, and `NOINHERIT`, all named
explicitly rather than inherited from server defaults. The application role owns
nothing — it is a grant recipient, never an owner.

#### Why the table list is named, not `ON ALL TABLES`

The database holds 23 tables. The application models 17. The remaining six are
`alembic_version` — Alembic's own bookkeeping, needed only by whoever runs a
migration — and the five tables reserved for features that were never built:
`hollidays`, `materials`, `preliquidated`, `services`, `uom` (TICKET-018).

The grant names the 17, and the sequences it needs are named too, because two
sequences in the live database (`materials_material_id_seq`,
`services_service_id_seq`) belong to reserved tables. `ON ALL TABLES` and `ON
ALL SEQUENCES` would have handed the running service full write access to all
six, and the ability to advance two counters it has no use for.

The alternative was considered and rejected: granting `SELECT` on all tables and
restricting only writes. It is simpler, and it leaves the reserved tables
readable by a credential that has no reason to read them.

**No privilege on the reserved tables is not a bug that will be fixed when those
features are built.** When one is built, the table gets a model, and the grant
list grows by exactly that table, in the same commit as the model. The
alternative — granting DML on tables the application does not model, in advance —
is the "allow everything now, restrict later" shape that stays unrestricted,
because nothing later ever re-audits it.

#### Reachability is enforced by `pg_hba.conf`, not by REVOKE

The application role must not be able to connect to another application's
database on the same instance. Two things are commonly confused here, and only
one of them works.

**`REVOKE CONNECT ... FROM PUBLIC` does not do this.** The revocation is *per
database*. It does not make the server-wide; it makes that one database
unreachable to everyone relying on the default, while every other database keeps
its `PUBLIC` CONNECT unchanged. An application that has run it and believes it
is isolated is not.

It is also someone else's change to make. Revoking `PUBLIC` on a database this
project does not own breaks whichever tenant depends on the default, from code
that has never heard of this file.

**`pg_hba.conf` does do this.** It is evaluated before any SQL runs, applies
across every database at once, and is scoped to a single role:

```
# TYPE     DATABASE     USER               ADDRESS        METHOD
host      <database>   <runtime>_app      <app-cidr>     scram-sha-256
host      all          <runtime>_app      0.0.0.0/0      reject
```

The deny-all line must come *after* the allow line — `pg_hba.conf` is
first-match — and both must sit above any broader rule already present. Reload
rather than restart so in-flight connections survive.

Step 4 of the SQL file gives the commands to locate the file, insert the rule
above the existing broader lines, and reload. Do not skip the verification: until
a cross-database connection has actually been observed to be rejected, the
isolation this section is credited with does not exist yet.

#### Before running

- Replace every `<placeholder>`. Do not leave a literal in place.
- Check the names are free, or you will collide with another application:

  ```bash
  docker exec -it <pg-container> psql -U <admin-user> -c '\du'
  docker exec -it <pg-container> psql -U <admin-user> -c '\l'
  ```

- Generate real passwords (`openssl rand -base64 32`). Never write a password
  into a file in this repository, or into a compose file. `.env` is gitignored;
  confirm it stays that way.
- Read the instance inventory (`SELECT datname, datacl FROM pg_database;`) so you
  know what currently relies on the `PUBLIC` default before changing anything.
  A `NULL` `datacl` means "default".

#### After running

The SQL file ends with verification queries, commented out because they are
checks rather than steps. Run them, the privilege tests **as `<runtime>_app`**.

| Check                                        | Expected |
|----------------------------------------------|----------|
| no capability attributes on the role         | 0 rows   |
| role owns no tables                          | 0 rows   |
| role `SELECT`                                | succeeds |
| role `INSERT` (then roll back)               | succeeds |
| role `CREATE TABLE`                          | fails    |
| role `DROP TABLE`                            | fails    |
| role `ALTER TABLE ... ADD COLUMN`            | fails    |
| role `CREATE INDEX`                          | fails    |
| role connecting to another app's database    | fails    |

The last one is the one to actually run from a different host. A permission
error rather than a connection rejection means the `REVOKE` ran but
`pg_hba.conf` did not take effect — the SQL file's step 4 is the fix.

A check that succeeds where it was expected to fail means the role has more
privilege than intended. Fix it before pointing the application at it.

#### Not automated, on purpose

- No `CREATE DATABASE` in the SQL file. The database is created empty by an
  administrator and then populated from the schema of record, so the schema
  always has exactly one source.
- No idempotency guards beyond the statements themselves. This is a short,
  reviewable, human-run file; it is not a deployment artifact. If it needs
  re-running, drop the role first and start again.
- No password generation in the script. A password generated by a script ends up
  in a compose file or a log.
- No provisioning of a second role. See above; a DDL role that does not own the
  schema cannot do DDL, and one that does own it defeats the boundary.

#### Relationship to the sibling project

A sibling application shares this PostgreSQL instance and has its own
provisioning file. The two are independent, and neither creates the other's
objects. They agree on two points, both of which are properties of the instance
rather than of any one application:

- the application role holds DML only, and ownership is never transferred to it
- reachability is enforced with `pg_hba.conf`, not with `REVOKE ... FROM PUBLIC`

The sibling's own documentation carries the same `pg_hba.conf` warning, which is
the reason this file cites it rather than substituting a grant for it.

#### See also

- `docs/deployment-guide.md` §2 for the operational sequence.
- `.opencode/skills/deploying-backend-vps/SKILL.md` for the general procedure;
  this section is a concrete instance of it.

## SETUP: ONLY FIRST TIME

> **The schema comes from [`infra/schema.sql`](infra/schema.sql), not from `init.sql`
> and not from the models.**
>
> `init.sql` is retired. It declares a foreign key PostgreSQL refuses (`TICKET-008`),
> and omitted `token_blacklist`, which every authenticated request queries (`TICKET-017`).
> `bootstrap.sh` ran `psql` without `-v ON_ERROR_STOP=1`, so it printed
> `✓ init.sql executed` even when the load failed.
>
> `infra/schema.sql` is a `pg_dump --schema-only` snapshot of the live database:
> 23 tables, labelled generated, carrying its provenance. It is the dev bootstrap
> and the source for the Alembic baseline revision, so the two cannot disagree.
>
> **Do not rebuild the schema from the SQLAlchemy models.** The models are stale
> against the live database — `alembic check` reports 94 pending operations — so a
> script generated from them
> loads cleanly and builds the *wrong* schema — a worse failure than a loud one.
> See `TICKET-019`.

```bash
# One time only: the development interpreter and its dev/test dependencies.
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt

# Fill in the local keys in .env (see .env.example): CORE_COMPOSE_COMMAND,
# CORE_DB_ADMIN_*, CORE_MINIO_ROOT_*, SEED_USER_*.

# Then bring the local stack up. Idempotent, and safe to re-run.
make setup-local
```

`make setup-local` creates this project's network, attaches it to the running
shared core, provisions this project's role, database, bucket and credentials,
applies `infra/schema.sql` plus `alembic upgrade head`, loads synthetic seed
rows, starts the API, and prints the resolved endpoints. It does **not** start
the shared PostgreSQL or MinIO: those belong to another project, which starts
them.

## RUN: NEXT TIME
```bash
# Bring up (idempotent — this is also all you need after a reboot)
make setup-local

# Prove the environment is coherent
make gate-local

# Serve the API with reload for the edit loop
make run-native
```

The core's location is **not** hardcoded here. It arrives through
`CORE_COMPOSE_COMMAND` in `.env`, which names the compose file of the project
that owns it. This project never edits or starts that file; it only attaches to
the running containers on the network it owns.

### WHAT THE MINIO CONTAINER CHANGE CHANGED

`minio-acme` now publishes its ports on **loopback (this host (Linux-Physical-Machine) to itself) only**
(`127.0.0.1:9000`, `127.0.0.1:9001`) instead of on every interface. Two
consequences, both load-bearing:

1. **The VPS stack cannot reach it yet.** `infra/vps/docker-compose.yml` dials
   `minio-acme` by container name on `my-dopamine-network`. Moving MinIO into its own
   compose project did **not** move it onto `my-dopamine-network` — it came up on that
   project's own prefixed network, `assync_as-sync-acme-network`. Compose cannot
   attach a container it does not own, so the attach is a manual step, already
   written into docs/deployment-guide.md §1 and repeated in the compose file:

   ```bash
   docker network connect <infra-net-name> minio-acme
   docker network inspect <infra-net-name> --format '{{range .Containers}}{{.Name}} {{end}}'
   ```

   Skip it and the API starts and reports healthy, then every upload and every
   photo download fails on DNS resolution. Nothing warns you at boot.

2. **A phone on the LAN can no longer load media.** Presigned URLs are signed
   with `MINIO_PUBLIC_ENDPOINT`, and with the S3 port bound to loopback there is
   no longer a listener at any LAN address. For local device testing, pick one:
   publish the S3 port on the LAN again (`"9000:9000"` in the MinIO compose), or
   forward it with an `alpine/socat` tunnel as `provider-portal-minio-dev-tunnel`
   does, or point the app at Caddy. For the VPS this is a non-issue: Caddy is the
   only public listener and terminates TLS for `MEDIA_DOMAIN`.

   `MINIO_PUBLIC_ENDPOINT` in `.env` was `192.168.10.30`, which is not this host
   (`192.168.10.31`) and does not answer on the LAN at all, so every URL the API
   handed out was dead on arrival. The LAN-correct value is the machine's mDNS
   name, `ratara5-SVT15115CLS.local`, which avahi (It open-source-software allows 
   computers and network devices to automatically discover and communicate with 
   each other on a local network (LAN) without manual IP configuration or DNS setup) 
   publishes and a phone on the same LAN resolves directly. A name rather than an 
   address, because this key is signed into every URL and must not move when a DHCP 
   lease rotates.

   `.env` currently holds `MINIO_PUBLIC_ENDPOINT=127.0.0.1`, which is correct
   *only* while the app runs in a simulator or another on-host client that shares
   this host's loopback namespace — that is why photos render there. It is not a
   LAN value: all of `127.0.0.0/8` is unreachable from any other device, so
   `127.0.0.1` or `127.0.0.2` signed into a URL fails on a real handset every
   time. Set this key to `ratara5-SVT15115CLS.local` (or a DHCP-reserved LAN
   address) before testing on a physical device.

### THE BUCKET AND ITS VOLUME ARE A SEPARATE PROBLEM

The port binding was necessary but not sufficient. `minio-acme` now runs under
the `assync` compose project, so its volume is `assync_acme_minio_data`, which is
**empty**. The 34 objects uploaded before the move are in
`infrastructure-companies-v2_acme_minio_data`, under the bucket
`acme-uploads-own-api`. A fresh `minio-acme` therefore serves no photos, and no
port binding changes that.

`.env` names `tecfrio-uploads-own-api` as `MINIO_DEFAULT_BUCKET`. That bucket did
not exist on the new volume, so the API failed its startup bucket check with
`AccessDenied` until the bucket and a service account scoped to it were created
(`tecfrio_access_key`, policy limited to that single bucket — not root
credentials, per `.env.example`).

Before this carries real traffic, decide which of these is true, because they are
not equivalent:

- **the historical objects are wanted** — attach the volume that holds them
  (`infrastructure-companies-v2_acme_minio_data`) and set
  `MINIO_DEFAULT_BUCKET=acme-uploads-own-api`
- **the new empty bucket is wanted** — nothing to migrate, but every photo
  referenced by an existing `photos` row is then a dead link that needs clearing
  or re-uploading. **This option was selected on 2026-09-30.**

Check with `mc ls local/<bucket> --recursive | wc -l`, never with a bucket
existence test: an empty bucket satisfies every check the API makes.

### TWO ORIGINS, TWO RUN MODES — DO NOT MIX THEM

`MINIO_ENDPOINT` is where *this process* dials the store; `MINIO_PUBLIC_ENDPOINT`
is the origin baked into presigned URLs, which the phone must resolve. They are
deliberately different values in the VPS stack, and `infra/vps/docker-compose.yml`
now pins both for the container instead of inheriting them from `.env`, because
`.env` is the host-run file where `MINIO_ENDPOINT=127.0.0.1` is correct and
`127.0.0.1` inside a container is the container itself.

## API USAGE  
```bash
# 1. Register (creates user + returns token)
curl -X POST /auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","user_name":"User","password":"secret123","user_role":"TECHNICIAN"}'
# → { "access_token": "eyJ..." }

# 2. Login (returns token)
curl -X POST /auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret123"}'
# → { "access_token": "eyJ..." }

# 3. List tickets (using token)
curl -X GET /tickets \
  -H "Authorization: Bearer eyJ..."
# → [ { "ticket_id": 1, "ticket_description": "...", ... } ]

# 4. Get single ticket
curl -X GET /tickets/1 \
  -H "Authorization: Bearer eyJ..."
# → { "ticket_id": 1, ... }

# 5. Create ticket
curl -X POST /tickets \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"1","ticket_date":"2026-07-07T00:00:00","ticket_description":"Broken pump","priority":"NORMAL","status":"OPEN","market_id":1,"equipment_id":1}'
# → 201 { "ticket_id": 1, ... }

Prerequisites for POST: market_id and equipment_id must reference existing rows in markets and equipments tables (TICKET-001 fix). The /tickets endpoints require a valid JWT Bearer token from /auth/login or /auth/register.
```  
### TICKET LIFECYCLE
OPEN -> ASSIGNED -> IN PROGRESS -> CLOSED  
OPEN -> CANCELLED  
IN PROGRESS -> PAUSED  

### MASTER DATA ENDPOINTS  
```bash
# List technicians
curl -X GET /technicians -H "Authorization: Bearer eyJ..."
# → [ { "technician_id": 1, "user_name": "John Technician" } ]

# Get single technician
curl -X GET /technicians/1 -H "Authorization: Bearer eyJ..."
# → { "technician_id": 1, "user_name": "John Technician" }

# List spares
curl -X GET /spares -H "Authorization: Bearer eyJ..."
# → [ { "spare_id": 1, "spare_name": "Filter", "price": 10.5 } ]

# Get single spare
curl -X GET /spares/1 -H "Authorization: Bearer eyJ..."
# → { "spare_id": 1, "spare_name": "Filter", ... }

# List markets
curl -X GET /markets -H "Authorization: Bearer eyJ..."
# → [ { "market_id": 1, "market_name": "Market A", "city": "City", "transport_cost": 100 } ]

# Get single market
curl -X GET /markets/1 -H "Authorization: Bearer eyJ..."
# → { "market_id": 1, ... }

# List equipment
curl -X GET /equipments -H "Authorization: Bearer eyJ..."
# → [ { "equipment_id": 1, "equipment_name": "Pump" } ]

# Get single equipment
curl -X GET /equipments/1 -H "Authorization: Bearer eyJ..."
# → { "equipment_id": 1, ... }

# List labsdls (laboratory standards)
curl -X GET /labsdls -H "Authorization: Bearer eyJ..."
# → [ { "labsdl_id": 1, "labsdl_name": "Normal", "labsdl_description": "", "hourly_rate": 50 } ]

# Get single labsdl
curl -X GET /labsdls/1 -H "Authorization: Bearer eyJ..."
# → { "labsdl_id": 1, ... }
```
All master data endpoints support `page` and `page_size` query parameters (defaults: page=1, page_size=50).

### PERMANENT DATA  
*Ticket 1:* CLOSED  
Checked States: OPEN, IN PROGRESS  
*Ticket 2:* CANCELLED  

## GIT NOTES  
### You need to know if any comit in branch main was written after the creation of a branch any-other-branch 
```bash
# Find the common ancestor (where the branch was created from)
base=$(git merge-base main any-other-branch)

# List commits on main made after that point
git log $base..main
```  

### You need to do a real dry-run merge (Safe, Reversible)  
```bash
git checkout main
git pull
git merge --no-commit --no-ff any-other-branch
git status
git merge --abort
```

### You need to update the branch main from branch any-other-branch 
```bash
git checkout main
git merge any-other-branch
git status
# Reolve conflicts (if there are any) 
# git add <resolved-file>
git push origin main
git commit -m "Merge branch 'any-other-branch' into main"
git push
```  

### API USAGE IN POSTMAN  
It's possible use POSTMAN DESKTOP.
**There, import `app-tickets-backend.postman_collection.json`**  

### DB USAGE
```bash
docker exec -it postgres-gci psql -U postgres

\c db_gestiket_acme
```

## IMPLEMENTING OPENSPEC  
Open spec is a npm package + repo in order to add agentic layer  
see https://github.com/LIDR-academy/lidr-specboot/tree/main  
Next, a summmary of lidr-specboot/README.md (and expand the instructions for items applicable to this project):  

### 1. Install and initialize openspec   
If use nvm:
```bash
install nvm --lts
nvm alias default lts/*
node --version # min 24.16.0
npm install -g @fission-ai/openspec@latest
openspec init # IN OTHER TERMINAL!
```
...

### 2. Import into your project 
... and commit: `chore: add agentic layer config (OpenSpec/specboot) (wip)`

### 3. Customize `/docs` for your project (Mandatory)  
** 3.1 Generate `api-spec.json` **  

** option a **

```bash
docker compose up -f ~/Documents/GoogleCloudProjects/docker-compose.yml postgres-gci
uvicorn app.main:app --reload --reload-dir app
curl http://localhost:8000/openapi.json -o docs/api-spec.json
```  
...

** option b **  
```bash
pip install pyyaml
python3.12 -m scripts.export_openapi
```

`scripts/export_openapi` must exist