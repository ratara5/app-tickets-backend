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

Use `ON_ERROR_STOP=1` on **every** `psql` invocation. Without it `psql` reports each
error and continues, and you end up with a half-built schema that looks deployed.

```bash
# Never reuse the shared instance's superuser for the app.
docker exec -i <pg-container> psql -v ON_ERROR_STOP=1 -U <admin-user> -d postgres <<'SQL'
\l
CREATE ROLE <app_role> WITH LOGIN PASSWORD '<generated-password>';
CREATE DATABASE <app_db> OWNER <app_role>;
REVOKE ALL ON DATABASE postgres FROM <app_role>;
SQL
```

Confirm the role cannot see other tenants' databases:

```bash
docker exec <pg-container> psql -v ON_ERROR_STOP=1 -U <app_role> -d <app_db> -tAc \
  "SELECT datname FROM pg_database WHERE datistemplate = false"
```

### Schema creation, in order of preference

1. **The app's own migration tool**, applied to a freshly created database. Before
   trusting it, prove it: run it against a disposable database, then check that
   upgrading again is a no-op afterwards.
2. **The app's ORM metadata** (`create_all`), then stamp the migration history,
   when the migrations are deltas that assume a base schema already exists.
3. A raw `init.sql` only if it is proven to run clean on a fresh database today.

Any of these can be wrong. Check before deploying:

- Does the schema script depend on an extension that must exist? A stock
  `postgres:16` image has only `plpgsql`, `uuid-ossp`, `pgcrypto`.
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

After the schema exists, compare it against what the code expects. Counts must agree;
a mismatch in either direction means drift, not success.

```bash
docker exec <pg-container> psql -U <app_role> -d <app_db> -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
```

### Seed data

Only reference or lookup data. Never seed rows owned by tenants, and never seed
credentials. Re-running a seed must be idempotent, and it must never run against a
database that already holds live data without an explicit human decision.

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
