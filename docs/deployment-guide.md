# Deployment Guide — app-tickets-backend on a shared VPS

How to stand up, update and roll back this backend on a Linux VPS that already runs
PostgreSQL and MinIO for other applications.

The **method** is stack-agnostic and lives in the skill
`ai-specs/skills/deploying-backend-vps/SKILL.md`. This file is the concrete instance:
this repository's values, this repository's commands, and this repository's known
defects. Read the skill for the reasoning; follow this file for the actions.

## Topology

```
                      ┌───────────────────────────────┐
   internet ──▶ caddy-app-tickets ──▶ api-app-tickets ──┼──▶ postgres-gci   (shared, no published port)
                (proxy + TLS)        (published on        └──▶ minio-acme    (shared, no published port)
                                      127.0.0.1:8000 only)
                              │
                              └── both on external network infra-net
```

- `postgres-gci` and `minio-acme` belong to other applications. Never stop, remove,
  rename, restart or reconfigure them. Never publish a port for them.
- Only `caddy-app-tickets` publishes ports (80/443). The API is published on
  `127.0.0.1:8000` so the proxy reaches it by name, not through the host.
- `infra-net` is the shared network. `caddy` carries the DNS aliases
  `api.example.com` and `media.example.com`, so the API signs object URLs for the
  public media host and still reaches MinIO over the private network.

## 0. Discover the estate

```bash
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
docker inspect postgres-gci --format '{{json .NetworkSettings.Networks}}'
docker inspect minio-acme   --format '{{json .NetworkSettings.Networks}}'
docker inspect postgres-gci --format '{{.Config.Image}}'
```

The image matters: `postgres-gci` runs a **custom** build that includes `pg_uuidv7`
(verified: PostgreSQL 16.13, `pg_uuidv7` 1.7). Stock `postgres:16` does not.

## 1. Attach to the shared network

```bash
docker network create infra-net        # safe if it already exists? it does not — check first
docker network connect infra-net postgres-gci
docker network connect infra-net minio-acme
docker network inspect infra-net --format '{{range .Containers}}{{.Name}} {{end}}'
```

Connecting a container to an extra network is additive: its existing endpoints and
published ports are untouched, so the other applications are unaffected.

## 2. PostgreSQL: role → database → schema → seed

### 2.1 Dedicated role and database

Never reuse the instance's superuser. A compromised API must not reach other apps'
data.

```bash
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres -d postgres <<'SQL'
\l
CREATE ROLE gestiket_app WITH LOGIN PASSWORD '<generated>';
CREATE DATABASE db_gestiket_acme OWNER gestiket_app;
REVOKE ALL ON DATABASE postgres FROM gestiket_app;
SQL
```

Then confirm isolation, as the app's own role:

```bash
docker exec postgres-gci psql -U gestiket_app -d db_gestiket_acme -tAc \
  "SELECT datname FROM pg_database WHERE datistemplate = false"
```

Only `db_gestiket_acme` and `postgres` (revoked) should be visible.

### 2.2 Schema — `deploy/schema.sql`, the dump of the live database

The schema comes from [`deploy/schema.sql`](../deploy/schema.sql). It is a
`pg_dump --schema-only` snapshot of the live database: 23 tables, 2 enum types, and
the `pg_uuidv7` extension. Its header records the source, the exact command, and the
commit it was generated from, and `tests/test_deploy_assets.py` fails if that header
is removed or if the file stops declaring itself generated.

```bash
# Plane 2: the TABLES. The database must already exist.
docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U "$DB_USER" \
    -d "$DB_NAME" < deploy/schema.sql
```

`init.sql` is **retired and deleted**. It failed in three measured ways: a
`FOREIGN KEY` joining `VARCHAR` to `SERIAL` that PostgreSQL refuses, after which
`psql` skipped every remaining table and the load still looked successful
(`TICKET-008`); a dependency on `pg_uuidv7`, which stock `postgres:16` does not ship
(`TICKET-007`); and no `token_blacklist`, which every authenticated request queries
(`TICKET-017`). `bootstrap.sh` also ran `psql` without `-v ON_ERROR_STOP=1` and
printed `✓ init.sql executed` regardless. It now defaults to `deploy/schema.sql`,
passes `ON_ERROR_STOP=1`, and verifies afterwards that `token_blacklist` exists.

`ON_ERROR_STOP=1` is not optional on any `psql` call. Without it `psql` reports each
error, continues, and exits 0 — which is how three separate tickets stayed invisible.

**Do not generate the schema from the SQLAlchemy models.** Measured against the live
database on 2026-09-27, the models are stale in nine structural places: they would
give `tickets.ticket_id` a `SERIAL` although its ids come from the external ticketing
system, replace the live `priority_type` and `status_type` enums with `VARCHAR`, drop
`TIMESTAMPTZ` to `TIMESTAMP`, change `photos.photo_id` from `text` to `SERIAL`,
revert `token_blacklist.jti` to `VARCHAR(36)`, omit the `spares.unit` foreign key, and
miss the audit columns' nullability. A script generated from them runs cleanly and
builds the **wrong** schema, which is worse than one that fails loudly, because
nothing reports it. The database is the ground truth; the models are a claim about
it. Tracked as `TICKET-019`.

That is also why the dump has 23 tables and not the models' 17: the 5 reserved
tables for unbuilt features (`hollidays` — with a double L, as the live database
spells it — plus `materials`, `preliquidated`, `services`, `uom`) exist in production
and are carried through deliberately. Decision pending, owned by `ratara5`, review
2026-12-27. See `TICKET-018`.

`deploy/schema.sql` is a **dev bootstrap and the source for the Alembic baseline**,
not a production path. Production runs `alembic upgrade head`, which cannot work yet:
the graph has two heads (`TICKET-009`), no revision creates the base tables
(`TICKET-014`), and two revision ids are 35 and 48 characters long, longer than
`alembic_version.version_num` (`TICKET-010`). Regenerate the dump from the live
database with the command in its own header, never by hand-editing it.

### 2.2.1 The migration job is wired, but is not yet the path

The `migrate` stage of the `Dockerfile` and the `migrate` service in
`deploy/vps/docker-compose.yml` exist so that migrations run from the **same build**
as the application:

```bash
docker compose -f deploy/vps/docker-compose.yml run --rm migrate alembic heads
```

`run --rm` is what makes it a job. The service carries `restart: "no"` and must never
be started with `up`: a supervised migration that fails would restart-loop and
re-attempt DDL against `postgres-gci`, which is shared with other applications.

Two things this deliberately does **not** do:

- It is not in the `entrypoint`. The API runs `gunicorn --workers 2`, so an
  entrypoint migration would execute twice, concurrently, on every replica.
- It is not `docker compose exec api …`. That form requires the app to be already
  running, so it migrates *after* the code that needs the new column is serving
  traffic. `run --rm` fixes the ordering and needs no running container.

**Do not put this in the deploy sequence yet.** The blockers above mean
`alembic upgrade head` still fails; the job exists so the baselining work can be
*executed and verified from the image*.

An earlier version of this image could not run migrations at all: `alembic` is in
`requirements.txt` so the package was installed, but only `app/` was copied, so
neither `alembic/` nor `alembic.ini` was present. The container started and passed its
healthcheck while `alembic upgrade head` failed on missing config.
`tests/test_deploy_assets.py` now guards that.

**Autogenerate is destructive until the models are trusted.** Until 2026-09-27
`alembic/env.py` exposed only 2 tables in `target_metadata`, so
`revision --autogenerate` reported **20 of the 23 live tables** as `drop_table`
(measured against a database built from `deploy/schema.sql`; Alembic excludes its
own `alembic_version`). Both defects are now fixed — the imports and a named
exclusion for the 5 tables that have no models — and the result is 0
`remove_table`, verified against a disposable database. `alembic check` still
belongs in CI so drift fails the build instead of being discovered in production,
and the models themselves are still stale. That is `TICKET-019`.

**Refuse to touch a populated database.** Check before writing anything:

```bash
docker exec postgres-gci psql -U postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='db_gestiket_acme'"
docker exec postgres-gci psql -U postgres -d db_gestiket_acme -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
```

A non-zero table count means: stop. This procedure is for a **new, empty** database
only. Never re-bootstrap over existing data, and never point `DB_NAME` at the live
database by accident.

**Then load the schema** with the `psql` command in §2.2, with
`-v ON_ERROR_STOP=1`. A non-zero exit status there means the load failed; do not
continue.

**Verify** — compare **sets**, not totals. A count is equally satisfied by the wrong
set of tables, and a count is what let a broken `init.sql` look loaded. The expected
side is the dump, because the dump is what you just loaded:

```bash
# expected: the tables the dump declares
grep -oE '^CREATE TABLE (public\.)?\w+' deploy/schema.sql | awk '{print $NF}' \
  | sort > /tmp/expected-tables.txt

# actual: what the database really has
docker exec postgres-gci psql -U postgres -d db_gestiket_acme -tAc \
  "SELECT tablename FROM pg_tables WHERE schemaname='public'" \
  | sort > /tmp/actual-tables.txt

diff /tmp/expected-tables.txt /tmp/actual-tables.txt && echo "table set matches"
```

Expect 23 tables and an empty `diff`. Any difference means the dump and the database
disagree — stop and reconcile before deploying.

**Alembic is not part of this procedure.** The history cannot bootstrap an empty
database yet: two heads (`TICKET-009`), no revision creates the base tables
(`TICKET-014`), and two revision ids exceed `alembic_version.version_num`
(`TICKET-010`). The baseline revision is derived from this same dump, which is why
the two cannot drift apart. Until that work lands, do not create an
`alembic_version` table by hand and do not stamp — a hand-made history table stamped
against an incomplete graph produces a green `alembic heads` and a database no
migration can actually repair.

### 2.3 Seed

Reference data only (units of measure, service catalogue). Never tenants, never
credentials. Must be idempotent, and never run against a database with live data
without an explicit human decision.

## 3. MinIO: user → bucket → policy → credentials → CORS

`mc` ships inside `minio-acme`, so run it there; the alias, the policy file and the
credentials then live in that container and disappear together.

```bash
docker exec -it minio-acme sh
```

```bash
mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc ls local                     # confirm acme-uploads is still free
```

**1. Dedicated user** — a new user has no policies, and a service account inherits its
parent's, so this is what the policy attaches to:

```bash
mc admin user add local app-tickets-uploads '<generated-secret>'
```

**2. Bucket** — the app creates it on first boot (`app/core/storage.py`), so creating it
here is optional. If you do, keep it private: presigned URLs are the access path.

```bash
mc mb local/acme-uploads
```

**3. Bucket-scoped policy**, written inside the container because `mc` reads it from
that container's filesystem:

```bash
cat > /tmp/policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket","s3:ListBucketMultipartUploads"],
  "Resource":["arn:aws:s3:::acme-uploads"]},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],
  "Resource":["arn:aws:s3:::acme-uploads/*"]}]}
JSON
mc admin policy create local app-tickets-uploads-only /tmp/policy.json
mc admin policy attach local app-tickets-uploads-only --user app-tickets-uploads
mc admin policy info local app-tickets-uploads-only
rm -f /tmp/policy.json
```

**4. Credentials** — the service account inherits the attached policy, so no
`--policy` flag is needed:

```bash
mc admin svcacct add local app-tickets-uploads \
  --access-key '<access-key>' --secret-key '<secret-key>'
```

Put those two values in `.env` as `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`. They can
touch `acme-uploads` and nothing else on the instance.

**5. CORS — not needed for this project.** The clients are React Native/Expo; CORS is a
browser mechanism and native `fetch` is not subject to it. Uploads go
client → API → MinIO, so the browser never contacts MinIO directly. Set bucket CORS only
if a web client is added later, and then on the bucket, not the server, so the other
tenants are unaffected. The decision table is in the skill's
`references/media-and-minio.md`.

## 4. Configuration and start

### 4.1 `.env`

```bash
cp .env.example .env
```

Fill in: `DB_USER`, `DB_PASSWORD`, `JWT_SECRET` (32+ bytes), `MINIO_ACCESS_KEY`,
`MINIO_SECRET_KEY`, `ACME_EMAIL`, and the three hostnames. `ACME_EMAIL`,
`API_DOMAIN` and `MEDIA_DOMAIN` are **required**: compose refuses to render without
them, because Caddy will not start on an empty address and a proxy that cannot start
would otherwise surface as a confusing TLS failure.

**Never `source .env`.** `ALLOWED_TYPES` is a JSON array, and bash strips its quotes,
which breaks the app's settings validation. The app reads the file itself through
`app/core/settings.py`; a shell reads only the individual values it needs.

```bash
grep -E "^(DB_NAME|DB_USER|DB_HOST|DB_PORT)=" .env   # to export one value by hand
```

`MINIO_ENDPOINT` must be exactly `media.example.com` with `MINIO_PORT=443` and
`MINIO_SECURE=true` — the address clients use. Changing it later invalidates every URL
already delivered to a phone, so decide it now.

### 4.2 Start

```bash
docker compose -f deploy/vps/docker-compose.yml config >/dev/null
docker compose -f deploy/vps/docker-compose.yml up -d --build
docker compose -f deploy/vps/docker-compose.yml ps
docker compose -f deploy/vps/docker-compose.yml logs --tail=50 api
```

Certificates are obtained on first proxy start. `ACME_EMAIL` must be set beforehand.

## 5. Gates

Do not continue past a failing gate. Record the output of each one.

**5.1 Tenancy, before and after** — the baseline is taken *before* step 1:

```bash
docker ps -a --format '{{.Names}}' | sort > /tmp/estate.txt
docker network inspect infra-net --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}' | sort >> /tmp/estate.txt
docker volume ls --format '{{.Name}}' | sort >> /tmp/estate.txt
docker exec postgres-gci psql -U postgres -d postgres -tAc \
  "SELECT datname FROM pg_database WHERE datistemplate=false" | sort >> /tmp/estate.txt
docker exec -it minio-acme sh -c 'mc ls local' | sort >> /tmp/estate.txt
# ... do the work ...
diff <(tail -n +2 /tmp/estate.txt) <(tail -n +2 /tmp/estate-after.txt)
```

Bare 64-character hex lines are anonymous volume ids that appear and vanish whenever
any container is recreated: ignore them. Anything else you do not own that disappeared
is an incident — stop, restore, report.

**5.2 Backup** — before touching shared state, and off-box for anything risky:

```bash
docker exec postgres-gci pg_dumpall -U postgres > /root/pg-backup-$(date +%F-%H%M).sql
chmod 600 /root/pg-backup-*.sql
grep -c "CREATE TABLE" /root/pg-backup-*.sql     # a dump with no CREATE TABLE is worthless
```

**5.3 Schema** — §2.2's verify block: the table **set** matches the models plus
`alembic_version`, 2 stamped revisions, no-op upgrade. Compare sets, not counts; a
matching total is not evidence.

**5.4 Health** — in-network, then public:

```bash
docker exec api-app-tickets curl -sf http://127.0.0.1:8000/openapi.json >/dev/null && echo in-network ok
curl -sf https://api.example.com/openapi.json >/dev/null && echo public ok
ss -ltn | grep -vE '127\.0\.0\.1'    # only the proxy's ports may be public
```

**5.5 Media round-trip** — the gate that actually catches storage breakage. Health
checks pass while photos are broken. From a network that is not the server: presign an
upload, `PUT` real bytes, presign a download, fetch it back, compare, delete. Then
upload a file **larger than 5 MiB** from the app, which is where the multipart policy
errors appear.

**5.6 Configuration** — `.env` holds no root credentials, and
`MINIO_ENDPOINT` equals the media host.

## 6. Update and rollback

Update: §5.2 backup → §5.1 baseline → rebuild → every gate in §5 again. Skipping
§5.5 is how photos silently stop loading.

Rollback: redeploy the previous image tag, then re-run §5.4 and §5.5. Roll back code
first; keep schema changes backward compatible. Never restore a dump over live data
without an explicit human decision and a fresh backup.

## Known defects in this repository

Tracked as pre-proposals; each blocks a clean, reproducible deployment.

| Ticket | Defect | Blocks |
|---|---|---|
| `TICKET-007` | `init.sql` needs `pg_uuidv7`; only the shared custom image has it, and nothing records that | reproducing this deployment on a server built from stock `postgres:16` |
| `TICKET-008` | `init.sql:115` foreign key maps `VARCHAR` to `SERIAL`; PostgreSQL refuses it and `psql` continues, skipping every later table | using `init.sql` at all, on any image |
| `TICKET-009` | two migration heads, so `alembic upgrade head` fails | the singular upgrade form |
| `TICKET-010` | revision ids of 35 and 48 characters exceed `alembic_version.version_num varchar(32)` | stamping without widening the column first |
| `TICKET-014` | every migration is a delta that assumes the base tables, so migrations cannot create a database | any reproducible path from empty |
| `TICKET-015` | the live database records only `0005` although `0004`'s foreign key is present, and its history table was hand-widened to `varchar(64)` | the next migration on the live database |
| `TICKET-016` | `bootstrap.sh` clones a repository that does not exist in this tree | the documented first-run path |
| `TICKET-013` | `ALLOWED_TYPES` JSON breaks if anything sources `.env` | automation that sources the file |
| `TICKET-011` | `PRESIGNED_TTL` is documented as seconds and consumed as hours | media link lifetime |
| `TICKET-012` | one `MINIO_ENDPOINT` value is used for both internal I/O and public signing | media URLs, unless the network alias is in place |
| `TICKET-017` | `init.sql` omits `token_blacklist`, which every authenticated request queries; now hand-patched as a stopgap | trusting `init.sql` for a new database |
| `TICKET-018` | 5 tables for unbuilt features exist in the live database with no model; `uom` holds 9 rows and a broken reference. Owner ratara5, review 2026-12-27 | building against an unreviewed shape |
| `TICKET-019` | the ORM models are stale against the live database in 6+ places, so `init.sql` cannot be regenerated from them | retiring `init.sql`, which is the fix for `TICKET-017` |
| `TICKET-020` | `etl/seed_db.sh` loads under `session_replication_role = 'replica'` and prints success unconditionally | trusting seeded data to satisfy its foreign keys |

## Stop the bleeding

```bash
docker compose -f deploy/vps/docker-compose.yml stop        # this app only
docker start postgres-gci && docker start minio-acme        # shared, if actually down
docker ps -a --format '{{.Names}}\t{{.Status}}'             # restart times
```

`postgres-gci` and `minio-acme` are shared: check `docker ps` for restart counts and read
their logs before restarting anything, and never recreate them.
