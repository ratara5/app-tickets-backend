# Bug: two revision ids are longer than Alembic's own `alembic_version.version_num VARCHAR(32)`

## Metadata

- **Summary**: `alembic stamp`/`upgrade` cannot record `0004_…` (35 chars) or `0005_…` (48 chars)
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment

## Description

Alembic creates `alembic_version.version_num` as `varchar(32)`. This project's descriptive
revision ids exceed that:

| Revision | Length | Fits |
|---|---|---|
| `0001`, `0002`, `7f4d68531ba6`, `cfec57761e8b`, `0003_resume_maintenance` | 4-23 | yes |
| `0004_align_photos_maintenance_id_fk` | 35 | **no** |
| `0005_add_upload_replaces_photo_id_fix_parent_tab` | 48 | **no** |

Any command that must write those ids fails:

```
psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)
```

**Impact:** migrations cannot be applied or stamped on a fresh database, and a long id will
break the same command on any environment created from scratch.

## Reproduction

```bash
docker run -d --name probe -p 5499:5432 -e POSTGRES_PASSWORD=x postgres:16
# create a role + database, then:
python -m alembic stamp heads
# sqlalchemy.exc.DataError: value too long for type character varying(32)
```

## Notes

- Interim workaround: create the schema from the SQLAlchemy models and create `alembic_version` at `VARCHAR(64)` before stamping; see `docs/deployment-guide.md` §2.2
  creates `alembic_version` at `varchar(64)` before stamping.
- Permanent options: shorten the two revision ids (requires a merge, see TICKET-009), or
  configure a wider version table. Note that changing an existing revision id invalidates any
  environment that already recorded it.
- No existing environment was found with a widened `alembic_version`; how the current databases
  were stamped should be confirmed before choosing an option.

## Resolution

**Resolved 2026-09-27.**

The 35- and 48-character revision ids no longer exist. The single revision is
`0001_baseline`, 14 characters, which fits the `varchar(32)` Alembic creates.

Verified on a disposable database built from `deploy/schema.sql`: `alembic stamp
head` succeeded and stored the id without any column being widened. The live
database's `varchar(64)` was hand-widened to fit the old 48-character id; it is
left alone, and its value is the one trace of the old history that git does not
hold, so read it before stamping.

One residue: `deploy/schema.sql` carries that widened `varchar(64)` forward, so
new environments inherit it. Harmless with a 14-character id. Fixing it means a
migration on the live database plus a regenerated dump, not a hand-edit of the
generated file.
