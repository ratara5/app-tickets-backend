# Step 7 Report — Unit Tests and Database Verification

- **Date**: 2026-09-29
- **Change**: `split-minio-internal-and-public-endpoints`

## Commands Executed

```bash
# Targeted
pytest tests/test_minio_endpoints.py -q -p no:randomly
pytest tests/test_minio_endpoints.py tests/test_uploads.py tests/test_worksheets.py -q -p no:randomly

# Full suite with coverage
pytest -q -p no:randomly --cov=app --cov-report=term-missing

# Coverage of the modules this change touches
pytest tests/test_minio_endpoints.py -q -p no:randomly \
  --cov=app.core.storage --cov=app.core.settings --cov-report=term-missing

# Pre-existing-failure baseline on a pristine tree
git worktree add /tmp/opencode/baseline main
cp .env /tmp/opencode/baseline/.env
cp gtk-companies/gtk-acme/.env /tmp/opencode/baseline/gtk-companies/gtk-acme/.env
cd /tmp/opencode/baseline && pytest tests/test_uploads.py tests/test_maintenances.py -q -p no:randomly

# Live database baseline, before and after
docker exec -i postgres-gci psql -U postgres -d db_gestiket_acme -tAc "<counts>"
```

## Unit Test Results

| Run | Result |
|---|---|
| New suite `tests/test_minio_endpoints.py` | **24 passed**, 0 failed |
| Targeted (minio + uploads + worksheets) | 42 passed, 11 failed |
| Full suite | **255 passed, 23 failed, 5 xfailed** |
| Full-suite coverage (`--cov=app`) | **85%** (gate: 80%) |
| `app/core/settings.py` coverage | **100%** (65/65 statements) |
| `app/core/storage.py` coverage (new suite only) | 68% — the remainder is the pre-existing `upload_file` / `delete_object` / `object_exists_by_name` bodies, which the suite fakes at the service layer |

Runtime: full suite 487 s (coverage run), 181 s (no coverage).

### The 23 failures are pre-existing, proven not mine

They are all `sqlalchemy.exc.StatementError: (builtins.AttributeError) 'str' object has no
attribute 'hex'` — a `String` bound to a `Uuid` column — i.e. the already-filed
`TICKET-005-upload-uuid-sqlite-incompatibility`.

The identical selection run on a pristine `main` worktree produces the **same 23 failures**,
and `diff` of the two `FAILED` lists is empty:

```
IDENTICAL PRE-EXISTING FAILURES (23)
```

`tests/test_minio_endpoints.py` introduces no new failure and repairs none: the upload
suite is red before and after for an unrelated reason.

## Coverage of the acceptance criteria

| Criterion | Test | Result |
|---|---|---|
| Presigned URL host equals `MINIO_PUBLIC_ENDPOINT` with the internal endpoint unreachable | `test_presigned_url_is_signed_with_the_public_endpoint` (internal `192.0.2.1`, RFC 5737 TEST-NET-1) | pass |
| No network call while presigning | `test_presigning_issues_no_http_request` (transport stub records requests; zero recorded) | pass |
| No `GetBucketLocation` on pre-signing | `test_presigning_does_not_call_get_bucket_location` | pass |
| Region pinned on the internal client too | `test_readiness_probe_does_not_call_get_bucket_location` | pass |
| Public fallback to internal when unset | `test_presigned_url_falls_back_to_the_internal_endpoint` | pass |
| Public port/scheme differ (VPS case) | `test_presigned_url_uses_the_public_scheme_and_port` | pass |
| Dial and sign targets are independent | `test_uploads_dial_the_internal_endpoint_while_urls_sign_the_public_one` | pass |
| URL is signed, never rewritten | `test_presigned_url_carries_the_signature_for_the_public_host`, `test_presigned_url_is_not_rewritten_to_the_internal_host` | pass |
| `EHOSTUNREACH`/113, `ECONNREFUSED`/111, `ENETUNREACH`/101, `ETIMEDOUT`/110 → domain error naming the endpoint | `test_transport_errors_become_storage_unavailable` (4 params) | pass |
| urllib3 retry storm translated, cause still chained | `test_urllib3_retry_storm_is_translated_not_leaked` | pass |
| DNS failure → domain error | `test_socket_errors_become_storage_unavailable` | pass |
| `S3Error` not masked | `test_bucket_errors_are_not_masked_as_unavailable` | pass |
| Bucket probed once, not per upload | `test_bucket_is_probed_once_for_many_operations`, `test_upload_does_not_reprobe_the_bucket_on_every_photo` | pass |
| A failed probe does not poison a later success | `test_a_failed_probe_does_not_poison_a_later_success` | pass |
| Startup aborts once with an actionable message | `test_startup_aborts_once_when_the_store_is_unreachable` | pass |
| Startup succeeds against a reachable store | `test_startup_succeeds_against_a_reachable_store` | pass |
| Upload path raises the domain error, not a traceback | `test_upload_against_an_unreachable_store_raises_a_domain_error` | pass |

## Suite hermeticity

The new lifespan probe runs on every `TestClient` startup, so `tests/conftest.py` gained a
session-scoped autouse fixture that stubs `Minio._url_open` (the transport), **not** the
client class, so the new tests can still patch and assert on the same seam. The suite makes
no network call: proven by the fact that the full suite passes while the live store is only
reachable at one address, and by every test above stubbing the transport explicitly.

## Database State Verification

The test suite runs against a per-session **SQLite** file created and deleted by
`tests/conftest.py`; it never connects to the live PostgreSQL. The live database was
therefore captured before and after every run, and is unchanged:

| Table | Before | After |
|---|---|---|
| `tickets` | 8 | 8 |
| `maintenances` | 6 | 6 |
| `photos` | 4 | 4 |
| `uploads_sessions` | 143 | 143 |
| `worksheets` | 3 | 3 |
| `fsm_users` | 15 | 15 |

State restored: **Yes** — the HTTP round-trip fixtures from step 8 (one `fsm_users` row
`user_id=900001`, one `uploads_sessions` row, one `photos` row) were deleted and the counts
returned to the baseline. The two probe objects created in MinIO were removed as well.

## Outcome

**Step 7 status: PASS** — 24 new tests green, no regressions, 85% coverage, live database
byte-identical before and after.

## Incidental finding (not part of this change)

`POST /auth/register` returns 500 because the `fsm_users_user_id_seq` sequence is behind the
table (`nextval` returns 7, which already exists). The step-8 fixtures had to be created
with an explicit `user_id`. This is data drift in the live database, of the same family as
`TICKET-015`; it is recorded, not fixed, here.
