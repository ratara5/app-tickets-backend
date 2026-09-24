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