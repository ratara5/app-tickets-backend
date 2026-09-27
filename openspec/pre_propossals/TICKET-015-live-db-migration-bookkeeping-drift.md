# Bug: the live database's migration bookkeeping contradicts its own contents

## Metadata

- **Summary**: the shared database records only one of the two migration heads, although the sibling head's change is already applied, so the next `alembic upgrade` will try to re-apply it
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment

## Description

Measured on the shared container `postgres-gci`, database `db_gestiket_acme`:

```bash
docker start postgres-gci
docker exec postgres-gci psql -U postgres -d db_gestiket_acme -tAc \
  "SELECT version_num FROM alembic_version"
# 0005_add_upload_replaces_photo_id_fix_parent_tab          <- one row only

docker exec postgres-gci psql -U postgres -d db_gestiket_acme -tAc \
  "SELECT conname FROM pg_constraint WHERE conrelid='photos'::regclass AND contype='f'"
# photos_created_by_fkey
# photos_maintenance_id_fkey                                <- 0004's change IS present
# photos_updated_by_fkey
```

`0004_align_photos_maintenance_id_fk` and `0005_add_upload_replaces_photo_id_fix_parent_tab`
are sibling heads of the same parent. Only `0005` is recorded, yet `0004`'s foreign key
exists in the database. The history therefore understates what has been applied.

Consequences:

- `alembic upgrade heads` sees `0004` as pending and attempts to apply it to a database
  that already has the change, which fails on the duplicate constraint.
- `alembic current` reports a state that does not match the schema, so it cannot be used
  as a deployment gate.
- The database was evidently patched by hand: `alembic_version.version_num` is
  `VARCHAR(64)`, although Alembic's own DDL creates `VARCHAR(32)` and no script in the
  repository creates it wider. That is consistent with someone fixing a failed migration
  manually, which is how the missing `0004` stamp went unnoticed.

**Impact:** the next migration on this database is likely to fail during deployment, on
the shared server, in the middle of a release.

## Reproduction

```bash
docker start postgres-gci
python -m alembic current                 # with DATABASE_URL pointed at the live database
python -m alembic upgrade --sql 0003_resume_maintenance:heads   # offline: shows what it would run
```

The offline output shows `0004` being scheduled for application even though its change
is present.

## Acceptance criteria

- The migration history of the live database is reconciled with its contents: either
  `0004` is stamped, or `0004` is recorded as a no-op with a comment.
- A repeatable, documented procedure exists to bring a drifted database back in line
  (stamp, or a baseline migration), and the next `alembic upgrade` on it is a no-op.
- `alembic_version` is created by the migration tooling itself, so a hand-patched column
  width is not required.
- Deployment checks compare the recorded history against the expected heads before
  applying anything.

## Notes

- The sibling defects are `TICKET-009` (two heads), `TICKET-010` (revision ids longer
  than the history column) and `TICKET-014` (no reproducible path from empty).
- Verifying this requires starting the shared container read-only; restore it to its
  previous state afterwards.
