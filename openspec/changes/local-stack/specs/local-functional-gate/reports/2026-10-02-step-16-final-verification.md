# Step 16 — Final verification

Date: 2026-10-02

## 16.1 `make gate` passes

```
$ make gate
...
275 passed, 1 skipped, 1 warning in 3.86s        # harness/contract stage
npx --no-install openspec validate --all
Totals: 7 passed, 0 failed (7 items)
PYTHONPATH=. venv/bin/python scripts/export_openapi.py --check
OpenAPI specification is up to date.
venv/bin/python -m pytest -q
706 passed, 1 skipped, 1 warning in 187.73s (0:03:07)

Gate passed.
```

exit 0.

## 16.2 `make gate-local` passes

```
$ make gate-local
==> Targeting (nothing is written until this passes)
    ✓ database is db_gestiket_acme
    ✓ bucket is app-tickets-local-uploads

==> Image
    ✓ container user is 'app', not root
    ✓ pytest is not importable in the image
    ✓ pandas is not importable in the image

==> Authenticated read
    ✓ POST /auth/login returned a token
    ✓ GET /auth/me returned 200

==> Write and delete
    ✓ POST /tickets created ticket 9301

==> Maintenance
    ✓ POST /maintenances created maintenance 01a0fec4-4473-7741-9ae2-c28721368766

==> Storage round trip
    ✓ POST /uploads/init created session 01a0fec4-44e6-7c2e-a29f-e86398203e22 (chunk_size 1048576)
    ✓ POST /uploads/chunk accepted chunk 0
    ✓ POST /uploads/complete produced a presigned URL
    ✓ public origin is loopback (127.0.0.1), the same origin a client uses locally
    in-container fetch did not match; trying from the host
    ✓ presigned GET returned byte-identical content (sha256 c883b7d8c262…)

==> Delete
    ✓ DELETE /maintenances/01a0fec4-4473-7741-9ae2-c28721368766 returned 204 and is gone
    ✓ DELETE /tickets/9301 returned 204
    ✓ GET /tickets/9301 returns 404

────────────────────────────────────────────────────────
gate-local  passed
────────────────────────────────────────────────────────
  image                    app-tickets-backend:local @ sha256:feb1308a6cfa
  database                 db_gestiket_acme @ 0003_join_table_keys
  bucket                   app-tickets-local-uploads
  object store (internal)  127.0.0.1:9000 secure=false
  object store (public)    127.0.0.1:9000 secure=false

  checks
    ✓ database is db_gestiket_acme
    ✓ bucket is app-tickets-local-uploads
    ✓ container user is 'app', not root
    ✓ pytest is not importable in the image
    ✓ pandas is not importable in the image
    ✓ POST /auth/login returned a token
    ✓ GET /auth/me returned 200
    ✓ POST /tickets created ticket 9301
    ✓ POST /maintenances created maintenance 01a0fec4-4473-7741-9ae2-c28721368766
    ✓ POST /uploads/init created session 01a0fec4-44e6-7c2e-a29f-e86398203e22 (chunk_size 1048576)
    ✓ POST /uploads/chunk accepted chunk 0
    ✓ POST /uploads/complete produced a presigned URL
    ✓ public origin is loopback (127.0.0.1), the same origin a client uses locally
    ✓ presigned GET returned byte-identical content (sha256 c883b7d8c262…)
    ✓ DELETE /maintenances/01a0fec4-4473-7741-9ae2-c28721368766 returned 204 and is gone
    ✓ DELETE /tickets/9301 returned 204
    ✓ GET /tickets/9301 returns 404

  limits of this result — read before quoting it as evidence

  * A local check is not a staging environment. It does not exercise the VPS
    network, its TLS origin, or its scheduling.
  * Local now reaches the shared core exactly as the VPS does — same container
    names, same in-network DNS — so a pass is stronger evidence of CONFIGURATION
    correctness than a local setup that had to work around the core. It is not
    evidence of DEPLOYMENT correctness. The gates that cover deployment-specific
    behaviour are docs/deployment-guide.md §5.4 (health) and §5.5 (media
    round-trip).
  * This gate exercises THIS PROJECT's access to the core. It does not check the
    core's own health, backup, patching or availability. A defect in the core's
    declaration appears here as a connection failure and is owned by the project
    that operates it.
```

exit 0.

> The first run of this command printed a Python traceback between the
> in-container fetch and its host fallback. It was not a failure — the fallback
> exists because the container reaches the object store by its in-network name,
> so a presigned URL naming the public origin is unreachable from inside it, and
> the gate then fetches from the host and matches byte for byte. But this output
> is meant to be pasted into a release note, where an unexplained stack trace is
> noise that makes the next reader doubt the result. The probe now discards its
> stderr, and the `in-container fetch did not match; trying from the host` line
> remains as the explanation. Re-run confirms 0 `Traceback` lines and exit 0.

## 16.3 The six no-touch files are byte-identical

Guard run directly, then confirmed independently against git:

```
$ venv/bin/python -m pytest tests/test_local_assets.py -k "no_touch or byte_identical" -v
6 passed, 41 deselected

  unmodified  infra/vps/docker-compose.yml
  unmodified  infra/vps/Caddyfile
  unmodified  docs/deployment-guide.md
  unmodified  infra/schema.sql
  unmodified  infra/provision/001-create-application-roles.sql
  unmodified  core/compose.yml
```

## 16.4 OpenSpec validation

```
$ npx --no-install openspec validate --all
✓ change/add-signed-ticket-status
✓ change/local-stack
✓ spec/master-data-api
✓ spec/photo-replace-delete
✓ change/split-minio-internal-and-public-endpoints
✓ spec/user-auth
✓ change/write-api-tests
Totals: 7 passed, 0 failed (7 items)
```

## 16.5 `git status` and the credential scan

```
$ git status --short
D  .coverage
 M .env.example
 M .gitignore
 M Dockerfile
 M Makefile
 M README.md
 M ai-specs/skills/dev-environment-parity/SKILL.md
 M app/core/settings.py
 M docs/development_guide.md
 M docs/learned-lessons.md
 M requirements.txt
 M tests/test_deploy_assets.py
 M tests/test_env_collection_settings.py
 M tests/test_minio_endpoints.py
?? .vscode/settings.json
?? infra/local/
?? openspec/changes/local-stack/
?? requirements-dev.txt
?? tests/test_local_assets.py
```

Every entry is accounted for: the modified files are this change, and the
untracked paths are this change's new artifacts. `.vscode/settings.json` is
intentional — task 9.5.

### `.coverage` was tracked, and this change had to untrack it

`git status` was not clean, and the reason was not this change's logic: `.coverage`
was **tracked in HEAD**, with no `.gitignore` rule. Running coverage — which this
change requires, at 13.3 — rewrote a committed binary file, so every developer who
ran the suite had a permanently dirty working tree. That defeats the point of this
step, which is to make "the tree is clean" mean something.

Fixed by adding `.coverage`, `.coverage.*`, `htmlcov/`, `.pytest_cache/`,
`.ruff_cache/` and `.mypy_cache/` to `.gitignore` and running `git rm --cached
.coverage`. The file stays on disk; it is simply no longer tracked. No commit was
made.

### The credential scan, and what it took to make it meaningful

The first scan compared every value in `.env` against the diff and reported a dozen
"leaks". Every one was a false positive, and each was worth understanding rather
than dismissing:

| Flagged | Actual value | Verdict |
| --- | --- | --- |
| `CORE_DB_ADMIN_USER` | `postgres` | matched the substring inside `postgres-gci` everywhere |
| `CORE_MINIO_ROOT_USER/PASSWORD` | `minioadmin` | the only hit is on a **`-` line** — pre-existing content this change *deletes* |
| `DB_USER`, `MINIO_ACCESS_KEY` | `gestiket_app` | an identifier already committed in `.env.example`; MinIO access key *names* are public, like usernames |
| `SEED_USER_EMAIL` | `local-seed@example.com` | `example.com` is reserved for documentation (RFC 2606); it is the seed identity, not a real account |

A scan that cries wolf is worse than no scan, because it trains the reader to
ignore it. Rescanned against only the values that are actually secret:

```
DB_PASSWORD              diff=False  newfiles=[]  clean
MINIO_SECRET_KEY         diff=False  newfiles=[]  clean
JWT_SECRET               diff=False  newfiles=[]  clean
SEED_USER_PASSWORD       diff=False  newfiles=[]  clean
CORE_DB_ADMIN_PASSWORD   diff=False  newfiles=[]  clean

RESULT: no secret value is disclosed
```

One observation, no action: the live `.env` uses `gestiket_app` as
`MINIO_ACCESS_KEY`, the same string as `DB_USER`. Conflating an object-store
identity with a database role name invites confusion when reading a config dump,
but it discloses nothing — the secret key beside it is generated and appears
nowhere. Noted, not changed, because changing it would add a second MinIO user to
a shared core and leave the old one behind.

## 16.6 This project's resources exist, and nothing else moved

Present on the shared core:

```
database present: db_gestiket_acme
role present: gestiket_app
alembic revision: 0003_join_table_keys
bucket present: app-tickets-local-uploads   (0 objects — clean after the gate)
```

Database role is unprivileged, so the local stack cannot escalate on a shared host:

```
rolsuper=false, rolcreatedb=false, rolcreaterole=false
```

Other projects, compared against the snapshot taken before this change's first
destructive step (13.7):

```
databases:        catalog_db, db_gci_acme, db_gestiket_acme, postgres   (same four)
buckets:          app-tickets-local-uploads (0)
                  provider-portal (0)
                  tecfrio-uploads-own-api (5)                          (same counts)
users:            gestiket_app      readwrite    <- this project's own, recreated by 13.7
                  tecfrio_access_key tecfrio-app <- another project: policy AND updatedAt unchanged
other schemas:    catalog_db 9 tables, db_gci_acme 22 tables
```

The only value that moved anywhere on the core belongs to this project and was
moved deliberately: `gestiket_app`, dropped and recreated in 13.7 to prove the
build works from nothing. `tecfrio_access_key` still carries its
`2026-10-01T02:29:40` timestamp — a day before this change began.

### The core containers were never restarted

```
postgres-gci  started 2026-10-02T13:03:37Z  restarts=0
minio-acme    started 2026-10-02T13:02:18Z  restarts=0
```

Both started hours before this change's first command and have zero restarts. This
is the load-bearing claim for the whole shared-core design: the local stack
attached itself to a running core without ever stopping it. `RestartCount=0` is
stronger evidence than "it still looks healthy", which a restart would also
satisfy.
