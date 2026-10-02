# Learned Lessons

## 1. Guard the Source Tree Against "Ghost Deletions" and Stray Copies

**Context**: On 2026-09-22, the entire `app/` package (61 tracked `.py` files) vanished from the working tree (only `__pycache__` remained), while a parallel copy with **modified** feature files (Director-sees-all / technician-assignment / reset-ticket logic) appeared under `alembic/app/`. `uvicorn app.main:app` failed with `Could not import module "app.main"`.

**Lessons**:
- A deletion like this is never visible in `git log` or reflog beyond a plain `reset: moving to HEAD` (unstage) — the destruction was a raw filesystem removal from a shell session that did not persist history. Diagnosis used **filesystem mtimes** (`app/api/__pycache__` written 08:25:45 = sources still present; dirs rewritten 08:27:38 = removal), **git reflog**, and **agent session logs** (opencode DB: no session touched the backend after Sep 6).
- An AI agent (Claude Code / Cursor / Codex) is the most plausible executor when no git record and no opencode record exists for a deletion. Such agents can operate on a repo that is *not* their advertised scope.
- Canonical sources (see `AGENTS.md` symlink-integrity rule) can be silently replaced by copies elsewhere; `alembic/` must contain **only** `env.py`, `script.py.mako`, and `versions/`.

**Rule**:
- Before trusting code state, run `git status --short` and `git ls-files app/ | wc -l`. An `app/` tree containing only `__pycache__` is broken.
- Never run `rm -rf` on a package unless `git status` proves the tree matches an explicit, reviewed intent.
- When a recovery keeps uncommitted feature work, **back it up to `/tmp` first**, `git restore` the canonical tree, re-apply only the deltas that differ (`git diff --no-index -r`), then remove the intrusion. Keep the backup until the work is committed.
- Add a guard note: `alembic/**/app/` is never a valid location for application code.

---

## 2. Uvicorn Reload Must Not Watch the Virtualenv

**Context**: `uvicorn app.main:app --reload` from the project root crashed with `OSError: OS file watch limit reached ... venv/lib/python3.12/site-packages/...` because the reloader (watchfiles) watches the whole tree, including tens of thousands of `venv/` files, blowing the per-user `fs.inotify.max_user_watches` budget. Same failure documented in the sibling frontend repo.

**Lesson/Rule**: Scope the reloader to source:
```
uvicorn app.main:app --reload --reload-dir app
```
If a watch limit still trips elsewhere, raise `fs.inotify.max_user_watches` via sysctl (or `/etc/sysctl.d/`), but `--reload-dir` is the primary fix.

---

## 3. Date-Bound Tests Must Be Deterministic; Red Suites Can Be Pre-Existing

**Context**: After recovery, `tests/test_tickets.py::test_add_wkd_success` failed with 403 (`Ticket is neither weekend ticket or holiday ticket`) on a weekday, because `create_new_add_wkd` requires `ticket_date.weekday() >= 5` or a holiday and the test payload used `datetime.now()`. Reaching the weekend path also exposed a latent `NameError: name 'Pause'` (the model was used but never imported — present in HEAD too). Separately, full-suite runs show pre-existing failures in `test_uploads.py` (`'str' object has no attribute 'hex'` — UUID column receiving a string under SQLite) and `test_maintenances.py` (`UNIQUE constraint failed: maintenances.ticket_id` — test-DB row leakage/ordering).

**Lessons/Rule**:
- Tests that depend on the current date are flaky by design; inject a fixed date (e.g. `WEEKEND_TICKET_DATE = "2026-08-01T00:00:00"`).
- A test failing on a code path that "can't happen today" often hides a real latent bug (missing import). Reach the branch to prove it.
- Before fixing (or committing) red tests, prove provenance with a stash A/B: `git stash push <files>` → run → `git stash pop`. If HEAD already fails, the failure is pre-existing and belongs to a separate ticket.

---

## 4. Bulk Deletes Desync the Session: "Expected to Update N Rows; 0 Matched"

**Context**: On 2026-09-24, `PATCH /tickets/{ticket_id}/reset` crashed with `sqlalchemy.orm.exc.StaleDataError: UPDATE statement on table 'photos' expected to update 2 row(s); 0 were matched.` `delete_maintenance_by_ticket` loaded `maintenance.photos` / `maintenance.worksheet` via `selectinload`, then removed those rows with `Query.delete(synchronize_session=False)`. The rows were gone in Postgres but the ORM session still tracked the loaded child instances; when the same flush deleted the parent, the unit of work tried to "unlink" the one-to-many children with `UPDATE photos SET maintenance_id = NULL WHERE … (2 ids)` — rows already gone, so 0 matched and the whole reset rolled back.

**Lessons/Rule**:
- `synchronize_session=False` bulk deletes are only safe when the rows were **never materialized in the session**. `synchronize_session=False` means exactly that — no session sync.
- Rule: delete children that are loaded as ORM instances with `db.delete(child)` (or use `synchronize_session="fetch"`); keep bulk `synchronize_session=False` only for collections that are provably not loaded.
- The "expected N row(s)" count is the number of **loaded objects**, not existing records — so "only delete if the records exist" would not fix this; the DELETE matches, the phantom UPDATE after it does not.
- The regression was invisible because `tests/test_reset_ticket.py` never seeded `Photo`/`Worksheet` rows. TDD: seed the rows that force the failing path before fixing.
- Model/DB drift is a second tripwire: `photos.maintenance_id` stayed `Integer` in the model while migration `0004_align_photos_maintenance_id_fk` made the column `Uuid`. The model must mirror the DB — the mismatch prevented UUIDs from being bound under SQLite tests and made prod uploads rely on driver ad-hoc adaptation.

---
## 5. A Runbook Can Be Confidently Wrong: There Was No Working Way to Create a Database

**Context**: On 2026-09-26 the VPS deployment runbook was reviewed end to end. Its schema
section read "load `init.sql` once, then `alembic upgrade head` for later releases". Both
commands fail, and each fails *quietly enough to look deployed*:

- `init.sql:13` needs `pg_uuidv7`, a third-party extension that only the shared custom image
  provides. Stock `postgres:16` does not ship it, so on a stock server the load "succeeds" with
  1 of 21 tables created.
- `init.sql:115` declares `FOREIGN KEY (created_by) → fsm_users(user_id)` as `VARCHAR → SERIAL`,
  which PostgreSQL refuses, skipping every table after it. **This one fails on every image**,
  including the shared one.
- The migrations are deltas that assume the base tables exist, so `alembic upgrade heads` on an
  empty database dies with `relation "maintenances_technicians" does not exist`.
- The graph has two heads, so `alembic upgrade head` fails outright with "Multiple head
  revisions are present".
- Two revision ids (35 and 48 chars) exceed Alembic's own
  `alembic_version.version_num VARCHAR(32)`, so Alembic cannot record them.

The only working fresh-install path found: build the schema from the SQLAlchemy **models** (the
source of truth), create `alembic_version` at `varchar(64)`, stamp `heads`, then migrate
normally. That procedure is now in `docs/deployment-guide.md` §2.2.

**Lessons/Rule**:
- A command that "works" because errors scroll past is the most dangerous kind. Every
  `psql`/`mysql` invocation in a script or runbook needs `-v ON_ERROR_STOP=1`, and a schema
  load must be followed by a comparison of *expected* against *actual* tables.
- Verify the bootstrap path before writing a runbook, not after: spin up the image the guide
  prescribes and run the exact commands in order.
- **Reproduce against the target's real image, and never generalise from a substitute.** The
  first version of this lesson reported that `pg_uuidv7` was "not available" and filed it as
  such. The real server runs `infrastructure-companies-postgres-gci` (PostgreSQL 16.13), which
  *does* ship `pg_uuidv7` 1.7 — the defect was never the extension, it was that the
  requirement is undocumented, so a server built from stock `postgres:16` breaks. Proving a
  bug on a convenient stand-in proves a bug *about the stand-in*. When the environment is
  shared infrastructure, read the running container (`docker inspect … .Config.Image`,
  `pg_available_extensions`) before writing the ticket.
- **The live system is the only ground truth about the live system.** Inspecting the running
  database overturned two assumptions: `tickets.created_by` is `integer` with a working
  foreign key (so `init.sql` is the stale artifact, not the schema of record), and that
  database has 23 tables against 17 in the models and 21 in `init.sql`. Its
  `alembic_version` is `varchar(64)` although no script creates that width, and it records
  only `0005` although `0004`'s foreign key is already present — so somebody patched it by
  hand and the next `alembic upgrade` there will try to re-apply `0004`
  (`TICKET-014`…`016`). Restore any shared container to the state you found it in.
- When two artifacts define the schema (`init.sql` vs models/migrations), they will drift.
  **Correction, 2026-09-27:** an earlier version of this line read "the models win; the other
  artifact is a liability until it is regenerated or retired". That is wrong, and acting on it
  would have made things worse. Measured against the live database, `alembic check` reports
  94 pending operations (37 type changes, 52 nullability changes, 2 sequence changes, 3 removals). A sample of them: `tickets.ticket_id` would gain a `SERIAL`, two live enums become
  `VARCHAR`, `TIMESTAMPTZ` becomes `TIMESTAMP`, `photos.photo_id` changes from `text`,
  `token_blacklist.jti` reverts an applied migration, the `spares.unit` foreign key is not
  declared at all). Regenerating `init.sql` from them yields a script that runs cleanly and
  builds the wrong schema — a quiet failure replacing a loud one. See `TICKET-019`.
  The corrected rule: **when two artifacts define the schema, do not assume either is of
  record — measure both against the live database before regenerating, deleting or trusting
  either.** Three artifacts is worse than two precisely because the third one looks like an
  authority.
- **A working application is not proof that its models describe its database.** The inference
  feels safe and is false: `token_blacklist.jti` is `uuid` in the live, working database and
  `String(36)` in the model, and `photos.photo_id` is `text` there with 12 rows behind it. A
  working application proves only that the columns it *uses* are compatible. Never regenerate
  a schema artifact from models on the strength of "the app runs".
- **A validated foreign key can still be violated if the loader disables triggers.** `uom` has
  one spare row pointing at a unit that does not exist, while `spares_unit_fkey` is validated
  with NO ACTION — because `etl/seed_db.sh:99` runs `COPY` under
  `session_replication_role = 'replica'`. Constraint enforcement that is switched off during
  load and never re-checked is not enforcement. See `TICKET-020`.
- `alembic upgrade head` failing is not a nuisance error: the deployment's core command does
  not run. `alembic heads` is the first thing to check when migrations misbehave.
- To prove a red suite is not yours, compare against a pristine tree rather than reasoning about
  it: `git worktree add /tmp/pristine HEAD`, copy the untracked `.env` across, run the same
  selection in both, then `git worktree remove`. Identical counts mean pre-existing
  (TICKET-001…006 here: 31 failed / 114 passed on both).
- **Skills should be agnostic; project runbooks should not.** A skill that hardcodes container,
  database, bucket or app names is a runbook in the wrong place, and shipping shell scripts
  inside a skill duplicates logic the agent can execute live and drift from. The method
  belongs in the skill with placeholders; the concrete values and the measured defects belong
  in the project's own runbook. That separation is also what let this correction be a
  one-file change instead of a rewrite.


## 6. One Setting With Two Owners Is a Latent Outage, and a Signed URL Is Never Rewritten

- **A single variable that serves two clients on opposite sides of a network is a
  configuration defect, not a convenience.** `MINIO_ENDPOINT` was both the backend's dial
  target and the origin baked into presigned URLs, so the only value that worked for both
  was a bare LAN address, because SigV4 signs the `Host` header and the phone cannot resolve
  `localhost` or a container name. A DHCP lease is not an address, it is a loan. The outage
  arrived on the next renewal, with no code change and no commit to blame — see
  `docs/post-mortems/2026-09-29-minio-endpoint-lease-outage.md` and `TICKET-012`.
- **"It has to be one value" is the conclusion of a conflated design, not a constraint of
  S3.** The moment two actors need two different answers from one setting, split the setting.
  `MINIO_ENDPOINT` now dials (127.0.0.1 on the host, `minio-acme` in Docker) and
  `MINIO_PUBLIC_ENDPOINT` signs, with a fallback to the internal value so no existing
  configuration changes behaviour.
- **A signed URL is immutable, and the mutation fails silently in production terms.** The
  signature covers `Host`; swapping the host in a delivered URL returns
  `403 SignatureDoesNotMatch`. Verified on the affected host: the real URL fetched from the
  Android emulator returns 200 with the exact bytes, and the same URL rewritten to
  `127.0.0.1` returns 403 from both the host and the emulator. Therefore the public origin
  is applied *at signing time*, and changing it later only affects newly issued URLs.
- **`minio-py` pre-signing is a network call unless you pin the region.** `get_presigned_url`
  calls `_get_region`, which answers from the client only when it was constructed with
  `region=`; otherwise it issues `GET /{bucket}?location=`. `__init__` always installs a
  credential provider, so the `not self._provider` early return never fires for this app.
  A second client bound to the public host without `region=` failed after **6.02 s** against
  an unresolvable host: the "fix" would have swapped the outage for a six-second stall per
  photo. With `region` pinned, pre-signing took **11.86 ms** and touched no socket.
- **Probe a dependency once, at startup, not on every request.** `ensure_bucket()` ran per
  upload, so one unreachable store became six connection attempts *per photo* through
  minio-py's `Retry(total=5, backoff_factor=0.2)`. One probe in the lifespan turns that into
  a single failure at boot. Memoize the success, never the failure, so a store that comes up
  later needs no restart.
- **Report a configuration mistake as a configuration mistake.** `EHOSTUNREACH` from a wrong
  setting should name the setting, the current value, and the fix; not surface as a urllib3
  retry traceback pointing at the network. Keep the cause chained for diagnosis, but render
  a compact chain (`errno 113 (EHOSTUNREACH)`), never `repr()` of a retry tree.
- **Cross-references, not duplicates.** The mobile repository records the mirror image of
  this incident in lessons 61/62 (the app can only resolve whatever host the backend signed).
  One canonical account here, one there, and an explicit link between them — the lesson is
  shared, the repository is not.
---

## 7. A Shared Dependency's Shape Is Not Its Interface

- **A network name is a decision, not a contract. The container names and ports are the
  contract.** A shared core can be composed four ways — everything in one compose, split per
  application, grouped by layer, inverted — so its network layout is free to change without
  anything about the dependency having changed. Consuming it correctly means depending on
  `postgres-gci:5432` and `minio-acme:9000`, and on nothing else. An earlier draft of the
  local stack declared two `external: true` networks to reach both, which was not cautious:
  it made this repository break on a rename it had no stake in, and the failure it bought in
  exchange was a DNS error that the API's own healthcheck passes straight through.
- **`network connect` state lives inside the container, so recreate is not restart.** A plain
  `docker restart` keeps a container's network attachments; re-creating it drops every one,
  silently. The network then still exists, still looks correct, and still has no members on
  the side that matters. This was observed directly: another application's network on the
  developer's host had no members because the core had been recreated. Any bring-up that
  attaches must therefore be idempotent and re-run every time, and must report which
  attachments it made — an attachment silently lost to a recreate is otherwise
  indistinguishable from one that was never made.
- **A find-and-replace that renames one half of a coupled pair is a routing change that
  reports success.** A rename of the deployed network name updated `name:` but left the
  network key and all five internal references alone. Compose resolves services through the
  *key*, so the file stayed valid, `docker compose config` passed, and the result was that
  Caddy, the API and the migration job would have been placed on another tenant's bridge — a
  public TLS entrypoint and the media origin, from an edit that looked complete. Two rules
  came out of it: a value that silently changes routing must never be changed by a tool that
  reports success, and the file's own comment two lines above had already warned against
  exactly that network.
- **A runtime attachment is a cache, and the provider owns the durable copy.** Attaching a
  shared container to a consumer's network with `docker network connect` puts the fact in the
  container, where the next recreate erases it with no log line and no error. The idempotent
  re-run every bring-up is the mitigation, not the fix: it makes the loss recoverable on demand
  and leaves the window open until someone runs the command. The fix belongs in the file the
  provider owns — each new application's network declared `external: true` on the core's own
  service — so the attachment is declarative and a recreate reproduces it. The direction is the
  lesson: a consumer must never edit the provider's compose to get this, and a provider who has
  not declared a consumer's network yet is the ordinary state, not a defect.
- **Read the provider's procedure; do not infer the provider's design.** The arrangement this
  project settled on was already documented by the project that operates the core, and the
  first draft here reasoned its way to a *different* answer by inspecting the host's networks
  and never opened that README. Inferring a shared dependency's intended shape from the
  accident of how a mirror is laid out is how two projects end up disagreeing about a system
  they are both running correctly.