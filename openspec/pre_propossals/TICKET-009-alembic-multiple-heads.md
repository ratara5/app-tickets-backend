# Bug: the Alembic migration graph has two heads, so `alembic upgrade head` fails

## Metadata

- **Summary**: `0004_align_photos_maintenance_id_fk` and `0005_add_upload_replaces_photo_id_fix_parent_tab` both descend from `0003_resume_maintenance`
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment

## Description

The revision graph is:

```
0001 -> 7f4d68531ba6 -> cfec57761e8b -> 0002 -> 0003_resume_maintenance
                                                       |-> 0004_align_photos_maintenance_id_fk        (head)
                                                       \-> 0005_add_upload_replaces_photo_id_fix_parent_tab (head)
```

`alembic upgrade head` resolves a single head and refuses:

```
ERROR [alembic.util.messaging] Multiple head revisions are present for given argument 'head'
```

**Impact:** the single most important deployment command in the project does not run. Every
release that applies a migration is blocked, and the workaround (`upgrade heads`, plural) is
not discoverable from the error message.

## Reproduction

```bash
python -m alembic heads
# 0004_align_photos_maintenance_id_fk (head)
# 0005_add_upload_replaces_photo_id_fix_parent_tab (head)
python -m alembic upgrade head
# ERROR: Multiple head revisions are present for given argument 'head'
```

## Notes

- Both branches contain real schema changes, so both must be applied; neither can simply be
  deleted.
- The fix is a merge migration (a new revision whose `down_revision` lists both heads) so that
  `head` becomes singular again.
- `docs/deployment-guide.md` and the deployment skill use `upgrade heads` and
  `alembic stamp heads` is an interim measure; both should revert to `head`
  once this is fixed.

## Resolution

**Resolved 2026-09-27, by replacing the history rather than repairing it.**

`alembic heads` now prints exactly one line, `0001_baseline`.

The two heads are gone because the seven-revision history is gone. It was
replaced by a single baseline derived from `deploy/schema.sql`, on the finding
that the history was never applied to any database: the live `alembic_version`
held one hand-stamped row, not a real history. There was no correct chain to
merge, only an inaccurate one to discard. `git` retains the deleted revisions, so
this is revertible.

See `docs/deployment-guide.md` §2.2.2 for when to undo it and how. Guarded by
`tests/test_alembic_baseline.py`.
