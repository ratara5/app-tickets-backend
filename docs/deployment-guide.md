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
database on 2026-09-27, `alembic check` reports 94 pending operations (37 type changes, 52 nullability changes, 2 sequence changes, 3 removals), so the models are stale
far past a handful of columns. The ones that matter most: they would
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

**Do not put this in the deploy sequence yet.** `alembic check` reports 94
pending operations, so autogenerate still writes a destructive revision. The job
exists so the remaining model work can be executed and verified from the image.

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
`remove_table`, verified against a disposable database.

The models themselves are still stale, and `alembic check` now measures it: **94
pending operations**, being 37 type changes, 52 nullability changes, 2 sequence
changes and 3 removals. That is `TICKET-019`, and it is why autogenerate is still
forbidden. The three removals are the reason it is not merely untidy:

| What autogenerate wants to remove | Consequence if applied |
|---|---|
| `spares.unit` foreign key (`spares_unit_fkey`) | the only thing making a `spares` row's unit verifiable — and the constraint `TICKET-020` is about |
| `maintenances.ticket_id` unique constraint | one maintenance per ticket stops being enforced |
| `technicians.user_id` index | a silent performance regression, no error |

It would also convert `photos.photo_id` from `text` to `Integer` and
`token_blacklist.jti` from `uuid` to `String(36)`, both against live data.

### 2.2.2 The baseline, and when to undo it

The Alembic history is one revision, `0001_baseline`, and it creates nothing.

**Why the seven previous revisions were deleted rather than repaired.** They
described how the schema got here, and that was never true. The live database was
built by hand and by the ETL loader; its `alembic_version` table was stamped by
hand and held one row, a 48-character revision id, inside a `varchar(64)` column
that Alembic's own DDL creates as `varchar(32)`. No environment had ever been
migrated by Alembic. So the history could not be replayed, and it could not even
be stamped: two heads, and ids too long for the column meant to hold them. There
was no correct history to repair, only an accurate one to write.

**How a database is built and brought under Alembic.** The schema comes from the
dump, never from the migration:

```bash
psql -v ON_ERROR_STOP=1 -d <db> < deploy/schema.sql   # build the schema
alembic stamp head                                   # record where it now stands
alembic upgrade head                                 # no-op, by design
```

`alembic stamp` writes only bookkeeping. It never alters a table, which is why it
is safe on the live database and why the baseline has empty `upgrade()` and
`downgrade()` bodies.

#### When to undo this, and how

Regret this only if one of these turns out to be true. Each is checkable before
you commit to anything.

| Trigger | How to undo |
|---|---|
| You need to **replay the old migrations** to build a schema from empty, step by step | `git revert` the squash commit. The seven revisions and their chain come back, and with them the two heads. |
| The live schema turns out **not** to be the truth for some environment (a second deployment whose schema differs) | Do **not** un-squash. Two schemas means one dump and one baseline are wrong; reconcile the environments first, then re-dump and re-baseline. |
| You discover a **column missing from the dump** | Fix the live database, regenerate `deploy/schema.sql` from it, then `alembic stamp head`. The baseline does not need to change: it is an anchor, not a copy. |
| A real migration is needed **now** | Write a revision with `down_revision = "0001_baseline"`. That is the normal path and needs no undo. |

What you give up by squashing: the ability to walk 0001→0005 incrementally. What
you keep: `deploy/schema.sql` as the single description of the schema, and a
bookkeeping table that fits its own column. `git` holds the deleted revisions, so
the undo is a revert, not an archaeology exercise.

**The one part that is not in git.** Stamping the live database overwrites its
`alembic_version` row. Until 2026-09-29 the current value was
`0005_add_upload_replaces_photo_id_fix_parent_tab`, and after the squash it named
a revision that no longer existed, so `alembic downgrade` had nowhere to walk to
either way. It is still the last surviving trace of the old history, and it is
the one piece of state the dump does **not** preserve — `pg_dump --schema-only`
emits the `alembic_version` table but not its rows. Read the value out **before**
stamping and keep it.

**Resolved on 2026-09-29.** Live is stamped `0002_widen_uom_factor` (head), so
the squashed history is now the one that matches reality. The old value is
preserved in `TICKET-009`, `TICKET-015` and this file, and in the pre-migration
backup.

**`alembic stamp` cannot do this on its own.** It reads the current revision to
compute the new one, so it fails with `Can't locate revision identified by
'0005_...'` — it cannot stamp over a revision it is unable to find. Write the
single row directly instead, which is what `stamp` does internally:

```sql
UPDATE alembic_version SET version_num = '0001_baseline';
```

Then `alembic upgrade head` works normally. This is bookkeeping, not schema: the
table holds one `varchar` row, and the dump above does not preserve it.

#### Guardrails

`tests/test_alembic_baseline.py` fails the build if a second revision reappears
(two heads), if the baseline gains a `down_revision`, or if any revision id
exceeds 32 characters. `alembic heads` must print exactly one line.

A stale detail worth knowing: `deploy/schema.sql` carries
`alembic_version.version_num` as `varchar(64)`, inherited from the hand-widened
live column. Harmless with a 14-character id, but the dump is the schema of
record, so that widening is now inherited by every new environment built from it.
Fixing it means a migration on the live database plus a regenerated dump — not a
hand-edit of the generated file.


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

### 2.3 Reference and demo data

**This is not a deployment step.** The loader (`etl/seed_db.sh`) never creates a
database, never alters a schema, and is never invoked by a deploy. It exists for
a fresh local database and for demos.

The loader separates two classes, because they are not the same thing:

- **Reference data** — `uom`, `hollidays`. No dependency on business rows, so
  these can be loaded anywhere. Production reference data is still a deliberate,
  human decision, not a side effect of deploying.
- **Business/demo data** — everything else, which requires `--allow-business-data`.
  This includes `materials`, `services` and `preliquidated`, which look like
  reference tables but are line items on a live record: `materials.maintenance_id`
  and `services.maintenance_id` reference `maintenances`, and
  `preliquidated.ticket_id` is `NOT NULL` and references `tickets`.

Always preview with `--dry-run` first. A CSV's filename becomes its target table,
so the allowlist is the boundary that stops a stray `tickets.csv` being copied
into the live `tickets` table.

```bash
./etl/seed_db.sh --db-host <container> --db-user <role> --db-name <database> --dry-run
./etl/seed_db.sh --db-host <container> --db-user <role> --db-name <database>
```

If a table is already non-empty it is left untouched, and the load is
non-destructive by construction: every table loads inside a transaction with
referential integrity enforced, so a bad reference fails the load instead of
landing. See `TICKET-020` for why the previous trigger-bypass version was
removed and `TICKET-021` for a precision defect found while rewriting it.

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

MinIO is configured with **two origins**, because the backend and the phone live on
different sides of the same storage:

| Variable | Job | VPS value | Why |
|---|---|---|---|
| `MINIO_ENDPOINT` + `MINIO_PORT` + `MINIO_SECURE` | where the **backend** dials the store | `minio-acme`, `9000`, `false` | the API's own traffic must not depend on a public identity, a DNS name, or a proxy hop |
| `MINIO_PUBLIC_ENDPOINT` (+ `MINIO_PUBLIC_PORT`, `MINIO_PUBLIC_SECURE`) | the origin **baked into presigned URLs** | `media.example.com`, `443`, `true` | the phone must resolve it, and the SigV4 signature covers `Host` |
| `MINIO_REGION` | the SigV4 region | `us-east-1` | pins the region so pre-signing is local instead of issuing `GET /{bucket}?location=` per URL |

`MINIO_PUBLIC_ENDPOINT` falls back to `MINIO_ENDPOINT` when unset, so an existing
single-value configuration keeps working unchanged. On the VPS, set **both**:

```bash
grep -E "^(MINIO_ENDPOINT|MINIO_PORT|MINIO_SECURE|MINIO_PUBLIC_|MINIO_REGION)=" .env
```

Rules that follow from the split:

- **A presigned URL is never rewritten.** The signature covers `Host`; changing the host
  in a delivered URL returns `403 SignatureDoesNotMatch`. The public origin is applied at
  signing time, and changing it later only affects newly issued URLs.
- **`MINIO_ENDPOINT` is never a LAN address.** A DHCP lease in that variable is a latent
  outage — this is exactly what broke on 2026-09-29 (see
  `docs/post-mortems/2026-09-29-minio-endpoint-lease-outage.md`).
- **The public origin is stable or it is nothing.** A domain served by Caddy, or a DHCP
  reservation. A bare lease takes photo loading down when the lease rotates.
- **Startup fails fast.** The bucket is checked once in the app lifespan, so an
  unreachable store aborts `uvicorn` with one message naming `MINIO_ENDPOINT` instead of
  producing a retry storm on every photo.

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
upload, `PUT` real bytes, presign a download, fetch it back, compare, delete. Confirm the
presigned URL's host is `MINIO_PUBLIC_ENDPOINT` and **not** `MINIO_ENDPOINT` — a wrong
public origin is invisible to every other gate and only shows up as broken photos in the
app. Then upload a file **larger than 5 MiB** from the app, which is where the multipart
policy errors appear.

**5.6 Configuration** — `.env` holds no root credentials, `MINIO_ENDPOINT` is an internal
address (never a LAN IP), and `MINIO_PUBLIC_ENDPOINT` is the media host.

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
| `TICKET-012` | ~~one `MINIO_ENDPOINT` value is used for both internal I/O and public signing~~ **RESOLVED 2026-09-29** by `MINIO_PUBLIC_ENDPOINT` + a pinned `MINIO_REGION`; see `openspec/changes/split-minio-internal-and-public-endpoints/` | — |
| `TICKET-017` | `init.sql` omits `token_blacklist`, which every authenticated request queries; now hand-patched as a stopgap | trusting `init.sql` for a new database |
| `TICKET-018` | 5 tables for unbuilt features exist in the live database with no model; `uom` holds 9 rows and a broken reference. Owner ratara5, review 2026-12-27 | building against an unreviewed shape |
| `TICKET-019` | the ORM models are stale against the live database (`alembic check`: 94 pending operations), so `init.sql` cannot be regenerated from them | retiring `init.sql`, which is the fix for `TICKET-017` |
| `TICKET-021` | `uom.factor_conversion` is `numeric(5,2)`, which cannot hold real conversion factors and truncates silently | any feature that converts between units |

## Stop the bleeding

```bash
docker compose -f deploy/vps/docker-compose.yml stop        # this app only
docker start postgres-gci && docker start minio-acme        # shared, if actually down
docker ps -a --format '{{.Names}}\t{{.Status}}'             # restart times
```

`postgres-gci` and `minio-acme` are shared: check `docker ps` for restart counts and read
their logs before restarting anything, and never recreate them.
