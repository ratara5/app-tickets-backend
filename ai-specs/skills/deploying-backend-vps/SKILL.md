---
name: deploying-backend-vps
description: Use when standing up, updating, rotating or rolling back a containerized backend on a Linux VPS whose PostgreSQL and MinIO containers are shared with other applications, when a deployment gate fails, or when uploaded media stops loading in clients after a release.
---

# Deploying a Backend on a VPS with Shared PostgreSQL and MinIO

**Input**: The project root, its deployment runbook (if any), and the names of the
shared containers and the network they sit on. If any of these are unknown, Phase 0
discovers them. Never invent container, database, bucket or role names.

**Core assumption**: PostgreSQL and MinIO are already running for other tenants.
This work attaches to them; it never replaces, restarts or reconfigures them.

## When to Use

- First deployment of a backend onto a VPS that already hosts other apps.
- Releasing a new version of such a backend.
- Rotating database or object-storage credentials.
- Diagnosing "photos/PDFs stopped loading after the release" in mobile clients.
- A tenant-isolation question: did this app disturb another app on the same box?

## Phase 0: Discover the Shared Estate

Never trust a runbook's container or network names; confirm them.

```bash
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'

# Which network(s) and ports each shared container is on
docker inspect <pg-container> --format '{{json .NetworkSettings.Networks}}'
docker inspect <minio-container> --format '{{json .NetworkSettings.Networks}}'
docker inspect <pg-container> --format '{{json .NetworkSettings.Ports}}'
docker inspect <minio-container> --format '{{json .NetworkSettings.Ports}}'

# The database image decides which SQL features exist
docker inspect <pg-container> --format '{{.Config.Image}}'
```

Docker's embedded DNS resolves any container **name** on a shared user-defined
network, not just compose service names.

## Phase 1: Network Attachment

Your app's containers must share a network with both shared containers. Creating a
network and connecting existing containers to it is additive: it adds an endpoint and
leaves their existing endpoints and published ports untouched, so other tenants are
not affected.

```bash
docker network create <shared-network>
docker network connect <shared-network> <pg-container>
docker network connect <shared-network> <minio-container>
docker network inspect <shared-network> --format '{{range .Containers}}{{.Name}} {{end}}'
```

Only risk to avoid: your app binding a host port that another process on the box
already listens on.

## Phase 2: PostgreSQL Role, Database, Schema

Provisioning and schema are **two different planes**, and keeping them apart is the
most important habit in this skill. They have different actors, different privileges,
and different failure modes.

| | Plane 1: provisioning | Plane 2: migration |
|---|---|---|
| Creates | the role, the database, the credentials | the tables, columns, indexes |
| Actor | a human, as an administrator | the app's own source, unattended |
| Privilege | superuser / `CREATEDB` | the app role only |
| Cadence | once per project, ever | every release |
| Failure means | the project never existed | that release is wrong |
| Belongs to | the shared estate | the application |

Neither plane creates the other, and no single command does both.

Use `ON_ERROR_STOP=1` on **every** `psql` invocation, without exception. Without it
`psql` reports each error and continues, and you end up with a half-built schema that
looks deployed. This one flag is the difference between a loud failure and a silent
one, and it is the most common defect in this area.

### Plane 1: the database is not the app's to create

`alembic upgrade head` creates tables. `prisma migrate deploy` creates tables. Neither
creates the database, and that is not an oversight — `CREATE DATABASE` cannot run
inside a transaction, and it needs privileges the application role must never hold.
Some Prisma commands will create a database for you, but that is a development-time
convenience, not a deployment path.

Create it as an administrator, once, deliberately, separately:

```bash
# Never reuse the shared instance's superuser for the app.
docker exec -i <pg-container> psql -v ON_ERROR_STOP=1 -U <admin-user> -d postgres <<'SQL'
\l
CREATE ROLE <app_role> WITH LOGIN PASSWORD '<generated-password>';
CREATE DATABASE <app_db> OWNER <app_role>;
REVOKE ALL ON DATABASE postgres FROM <app_role>;
SQL
```

**Why this must not happen from the app's own `docker compose up`.** The shared
instance hosts other tenants' databases. If the application's compose file can create
the role and the database, then:

- the app container must hold administrative credentials, so a compromise of the app
  is a compromise of every other tenant on the server;
- the create becomes a second, unaudited path to the same state, and it races with
  any other create;
- the database's lifetime becomes coupled to the app container's, which is false —
  the data outlives the deployment, and `compose down` must never imply otherwise;
- the role's password must live somewhere, and a compose file is the wrong place for
  a credential.

A tenancy on a shared server is provisioned by whoever administers the server. The
application is a client of that tenancy, not its owner.

Confirm the role cannot see other tenants' databases:

```bash
docker exec -i <pg-container> psql -v ON_ERROR_STOP=1 -U <app_role> -d <app_db> -tAc \
  "SELECT datname FROM pg_database WHERE datistemplate = false"
```

### Plane 2: the schema, from the app's own source

Plane 2 comes from the application's own migration tool, applied as a one-shot job
built from the same source as the running app. In order of preference:

1. **The app's own migration tool**, against an already-created database. Prove it on
   a disposable database first: migrate, then migrate again and confirm the second run
   is a no-op.
2. **A schema dump of the real database**, when no trustworthy migration history
   exists. This is a bootstrap, not a production path — see below.

#### When the ORM and the database disagree, the database is right

If an ORM is in play, its models and the live database will eventually disagree. The
database is the ground truth; the models are a claim about it, and the models can be
wrong. When they are, a script generated from the models loads cleanly and builds the
**wrong** schema — strictly worse than a script that fails loudly, because nothing
tells you it is wrong.

So reconcile the models to the database first, and only then generate anything. Do not
generate from unreconciled models, and do not "repair" a broken schema file by
regenerating it from the ORM. A file that is broken loudly today was doing you a
favour.

#### If there is no migration history: dump, then baseline

When the schema predates the migration tool, the history is usually incomplete — often
a single revision that creates one table and assumes the rest already exist. That
cannot bootstrap an empty database, and `upgrade head` fails partway.

Dump the real schema and use it as the source for a baseline revision, so the history
becomes replayable from empty:

```bash
docker exec <pg-container> pg_dump -U <admin-user> --schema-only \
  --no-owner --no-privileges -d <app_db> > schema.sql
```

`--no-owner` is not optional: without it `pg_dump` emits `ALTER … OWNER TO <role>` for
whichever role happened to own the live objects, and the file then fails on any server
where that role is named differently. `--schema-only` is not optional either: it keeps
production rows out of the repository.

One dump, two outputs — the dev bootstrap and the baseline revision. Deriving both
from a single snapshot is what makes them incapable of disagreeing.

Label any generated artifact as generated and record its provenance (source, command,
commit, date). An unlabelled generated file is read as hand-maintained, edited by hand,
and diverges silently. A test should assert the header survives, so the contract
cannot be quietly dropped.

### Running migrations as a job, not a service

Migrations are a one-shot job that exits. They are not a supervised process.

- Never `restart: unless-stopped` a migration. One failure becomes a restart loop
  re-hammering a database shared with other tenants.
- Never `compose exec <app> alembic …`. It requires the app to already be running, so
  the migration lands *after* the code needing the new column is serving traffic.
- Build the job from the same source as the app, so "what migrated" and "what runs"
  can never be different code. A separate `migrate` stage in the same Dockerfile plus a
  `run --rm` service in the same compose file is the shape that guarantees this.

```yaml
migrate:
  build:
    target: migrate          # same Dockerfile, same commit as the app
  command: ["alembic", "upgrade", "head"]
  restart: "no"             # a job exits; it is not a service
  networks: [infra-net]     # reaches the database, like the app
  # no published ports: a job has no traffic to receive
```

```bash
docker compose run --rm migrate                    # on a new release
docker compose run --rm migrate alembic heads      # prove the scripts are in the image
```

### Make drift a build failure, not a discovery

A one-time reconciliation rots. Wire drift detection into CI so the models can never
silently diverge again:

```bash
alembic check        # == revision --autogenerate --check; non-zero on any difference
```

It needs a database, so it belongs in a CI job with a throwaway PostgreSQL — not in a
unit-test suite required to run without one.

**Autogenerate is destructive until the metadata is trustworthy.** If the ORM metadata
does not hold the full schema, autogenerate reports the missing tables as `drop_table`
operations, and applying that output deletes live data. Fix the metadata first, count
the tables the metadata holds against the tables the database holds, reconcile any
difference by hand, and confirm the tool reports no operations before you let it write
anything.

### Things to check before deploying

- Does the schema depend on an extension that must exist? A stock `postgres:16` has
  only `plpgsql`, `uuid-ossp`, `pgcrypto`.
  ```bash
  docker exec <pg-container> psql -U <admin-user> -d <app_db> -tAc \
    "SELECT name, default_version FROM pg_available_extensions WHERE name = '<extension>'"
  ```
  An empty result means the script will fail halfway. Use the same custom image the
  other apps' databases were built on, or install the extension.
- Does a foreign key join mismatched column types (`VARCHAR` to `SERIAL`, say)? It
  cannot be created and the rest of the script still runs.
- Are there multiple migration heads? `upgrade head` then fails ambiguously. Use the
  plural form and stamp every head.
- Are revision identifiers longer than the history table's version column? They
  truncate or fail. Check the column width against the longest identifier.

### Verify the schema is what the code expects

```bash
docker exec <pg-container> psql -U <app_role> -d <app_db> -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
```

A count is the weakest check available: a script that skips every table after its first
error can leave the right number by coincidence. Compare table **sets**, not counts. A
dump missing one table still boots, and the application then fails on the routes that
need it — and if that table is on the auth path, it fails open.

### Seed data

A third plane, and the most dangerous to get wrong. Only reference or lookup data. Never
seed rows owned by tenants, and never seed credentials.

A seeder that disables referential integrity to get data in will load clean and hide
every violation it caused. Do not set `session_replication_role = replica`; do not defer
constraints to paper over an ordering problem; do not use a row count to decide
success. Re-running a seed must be idempotent, and it must never run against a database
that already holds live data without an explicit human decision. If a load has to
disable constraints to succeed, it must verify afterwards that the constraints hold.

### Adapter table

The doctrine is the same in every project; only the migration adapter changes.

| | This project (Alembic) | Sibling project (Prisma) |
|---|---|---|
| Plane 2 command | `alembic upgrade head` | `prisma migrate deploy` |
| Creates tables | yes | yes |
| Creates the database | no | no |
| Plane 1 | `createdb` as admin, once | `createdb` as admin, once |
| Schema of record | the generated dump | `schema.prisma` + `migrations/` |
| Dev bootstrap | `psql -f <dump>` | `migrate deploy` on a fresh database |
| Run as | one-shot `migrate` job | one-shot `migrate` job |
| Drift gate | `alembic check` in CI | `prisma migrate diff` in CI |
| Extra artifact to maintain | one generated dump | **none** |

The asymmetry in the last row is the point. Prisma was adopted together with the
schema, so `migrate deploy` replays a complete history onto an empty database and
there is nothing else to keep in step. Alembic was adopted after the schema existed, so
this project owns a hand-built baseline. A project that already has Prisma should
**not** add an inferred `init.sql`: it would be a fourth artifact describing the same
schema, and it would drift.

For how this doctrine reaches a second repository, see `ai-specs/harness-ia.md` §6.

## Phase 3: MinIO User, Bucket, Policy, Credentials, CORS

`mc` ships inside the MinIO server image, so run it there: the alias, policy files and
credentials all live in that one container's filesystem and disappear when it does.

```bash
docker exec -it <minio-container> sh
```

```bash
mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc ls local                      # confirm the app's bucket name is still free
mc admin user info local <app-user>
```

**User → policy → credentials**, in that order. The policy is what scopes the
account, and the service account inherits it:

```bash
# 1. Dedicated user for this app
mc admin user add local <app-user> '<generated-secret>'

# 2. Policy file: least privilege for ONE bucket. Write it inside the container,
#    because mc reads it from the container's own filesystem.
cat > /tmp/<app>-policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket","s3:ListBucketMultipartUploads"],
  "Resource":["arn:aws:s3:::<app-bucket>"]},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],
  "Resource":["arn:aws:s3:::<app-bucket>/*"]}]}
JSON

# 3. Create it, then attach it to the user
mc admin policy create local <app-policy> /tmp/<app>-policy.json
mc admin policy attach local <app-policy> --user <app-user>
mc admin policy info local <app-policy>

# 4. Credentials for the app: a service account inherits the user's policies,
#    so --policy is unnecessary once step 3 is done.
mc admin svcacct add local <app-user> --access-key '<access-key>' --secret-key '<secret-key>'

# 5. Bucket. Skip this if the app creates its own bucket on first boot.
mc mb local/<app-bucket>
rm -f /tmp/<app>-policy.json
```

Two things that bite:

- `mc admin user add` is not a credentials step. A service account is. The app
  authenticates with the service account's access key, never the user's secret.
- Granting the whole bucket also needs the `ListBucket`-class actions on the bucket
  ARN itself. Without them, uploads above the multipart threshold fail with
  `AccessDenied` while small ones succeed, which looks like a size bug.

### CORS: when it is actually required

CORS is a **browser** mechanism. It applies only to requests that a browser's
JavaScript makes directly to MinIO.

| Path | Needs bucket CORS? |
|---|---|
| Mobile/native app fetches a presigned URL | **No.** No CORS enforcement outside a browser. |
| App uploads by POSTing to its own API, which then talks to MinIO | **No.** The browser never contacts MinIO. |
| Browser app uploads directly to MinIO with a presigned PUT | **Yes.** |
| Browser app reads a presigned URL via `fetch`/XHR | **Yes.** |
| Browser renders a presigned URL in an `<img>` tag | **No.** Plain image loads are not CORS-checked. |

So for a mobile-only backend, skip this step entirely; for a web client, set it on
the **bucket**, not the server, so other tenants are unaffected:

```bash
cat > /tmp/<app>-cors.json <<'JSON'
{"CORSRules":[{"AllowedOrigin":["https://<app-domain>","http://localhost:<dev-port>"],
 "AllowedMethod":["GET","PUT","POST","HEAD"],"AllowedHeader":["*"],"MaxAgeSeconds":3000}]}
JSON
mc cors set local/<app-bucket> /tmp/<app>-cors.json
mc cors get local/<app-bucket>
rm -f /tmp/<app>-cors.json
```

The server-wide `MINIO_API_CORS_ALLOW_ORIGIN` environment variable is the
alternative, but it applies to every bucket in the instance. Prefer the bucket-scoped
configuration unless you are certain that is acceptable for the whole box.

## Phase 4: Configuration and Start

Credentials go in the app's environment file, never in a compose file or in version
control. Generate them; do not hand-write passwords in a runbook.

```bash
docker compose config >/dev/null          # catches interpolation and syntax errors
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 <api-service>
```

Confirm the app resolved its own configuration rather than a default, and that the
object-storage endpoint it holds is the address **clients** use, not the internal
container name. Presigned URLs are signed for one host; a mismatch produces `403`
`SignatureDoesNotMatch` or CORS failures that look like network problems.

## Phase 5: Gates

Do not proceed past a failing gate; fix it and re-run. Record each gate's output.

1. **Tenancy, before and after.** Snapshot the shared estate, and diff it:
   ```bash
   docker ps -a --format '{{.Names}}' | sort > /tmp/estate-after.txt
   docker network inspect <shared-network> --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}' | sort >> /tmp/estate-after.txt
   docker volume ls --format '{{.Name}}' | sort >> /tmp/estate-after.txt
   docker exec <pg-container> psql -U <admin-user> -d postgres -tAc \
     "SELECT datname FROM pg_database WHERE datistemplate=false" | sort >> /tmp/estate-after.txt
   docker exec -it <minio-container> sh -c 'mc ls local' | sort >> /tmp/estate-after.txt

   diff <(tail -n +2 /tmp/estate-before.txt) <(tail -n +2 /tmp/estate-after.txt)
   ```
   Bare 64-character hex lines are anonymous volume ids: they appear and vanish
   whenever any container on the box is recreated. Ignore them. Anything else that
   disappeared belongs to another tenant and is an incident. Changes matching only
   your own role, database, bucket, containers and volumes are expected.
2. **Backup exists and is restorable-shaped**, taken before you touched shared state.
   ```bash
   docker exec <pg-container> pg_dumpall -U <admin-user> > /root/pg-backup-$(date +%F-%H%M).sql
   chmod 600 /root/pg-backup-*.sql
   ```
3. **Schema**, Phase 2: object count and history state agree with the code.
4. **Health**, from inside the network and from the public entry point.
5. **Media round-trip.** This is the gate that actually catches storage breakage:
   presign an upload, upload bytes, presign a download, fetch it back, then delete.
   A health check passes while media is broken.
6. **No data ports exposed.** Only the reverse proxy publishes ports; the database
   and object store publish none.

## Phase 6: Update and Rollback

Update: take a backup, snapshot the estate, apply the new image, re-run every Phase 5
gate. A release that skips gate 5.5 is how photos silently stop loading.

Rollback: restore the previous image tag, then re-run the gates. Roll back code
first; a schema change that is backward compatible keeps the old code working.
Never roll back by dropping objects or restoring a dump over live data without an
explicit human decision and a fresh backup.

## Guardrails

- Never `stop`, `rm`, `rename`, `restart` or recreate a shared container, and never
  change its published ports, environment or volumes. Add to it; never mutate it.
- Never grant a wildcard (`s3:*`, `ALL`) policy. Scope to one bucket.
- Never let the app run as the database superuser or as the object-store root user.
- Never write credentials into compose files, runbooks or commits. Generate them.
- Never let one of your tenants' paths reach into another tenant's objects; enforce
  it in the application, and give the storage credentials only the scope to limit
  the blast radius.
- Never accept a half-built schema as deployed. Grep command output for `ERROR`.
- Never add a dependency on a non-standard extension without checking it exists on
  the target image, and without saying so in the runbook.
- Never assume a runbook's names are current; confirm them in Phase 0.

## Resources

- `references/media-and-minio.md` — presigned URL contract, multipart thresholds,
  backup and restore, CORS decision detail.
- `references/env-matrix.md` — required configuration per component, and the traps
  in parsing `.env` files that contain JSON.
- `references/troubleshooting.md` — symptom-first diagnosis table.
- `references/report-template.md` — the deployment report and its gate evidence.

## Quick Reference

```bash
# discovery
docker inspect <pg-container> --format '{{json .NetworkSettings.Networks}}'

# postgres, always with ON_ERROR_STOP
docker exec -i <pg-container> psql -v ON_ERROR_STOP=1 -U <admin-user> -d <app_db> -f -

# minio, from inside the server container
docker exec -it <minio-container> sh

# backup before touching shared state
docker exec <pg-container> pg_dumpall -U <admin-user> > backup.sql

# tenancy diff
diff <(tail -n +2 before.txt) <(tail -n +2 after.txt)
```
