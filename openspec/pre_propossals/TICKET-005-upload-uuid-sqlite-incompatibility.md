# Bug: UploadSession UUID column incompatible with SQLite test environment

## Metadata

- **Summary**: UUID column type in UploadSession causes SQLAlchemy error when querying with string values in SQLite
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: backend, database, testing

## Description

The `UploadSession.upload_id` column in `app/models/upload.py:12` is defined as `Column(Uuid, ...)` which stores UUIDs as binary (BINARY(16)) in PostgreSQL. When filtering with a string value in SQLite (used for testing), SQLAlchemy tries to convert the string to binary UUID using `value.hex`, which fails with `AttributeError: 'str' object has no attribute 'hex'`.

**Impact:** All upload endpoints (init, chunk, status, complete) fail when running tests with SQLite.

**Notes:**
- This is a PostgreSQL-specific type that doesn't work with SQLite
- The `save_upload_session` receives `upload_id` as a string and stores it directly, but queries expect a UUID object

## Reproduction

Run any upload endpoint test with SQLite backend → 500 error with `'str' object has no attribute 'hex'`

## Resolution

Fixed. The ticket's stated impact was that all upload endpoints fail on SQLite,
and `tests/test_uploads.py` passes 16 tests.

The specific fix was at the boundary rather than in the type: `upload_id` remains
`Column(Uuid, ...)`, and the repository/receive path converts the incoming string
once, at the edge, instead of letting a string reach a filter that expects a
`UUID` and call `.hex` on it. Typed generically as `Uuid` rather than
`postgresql.UUID`, which is what allows SQLite to store it as text.
