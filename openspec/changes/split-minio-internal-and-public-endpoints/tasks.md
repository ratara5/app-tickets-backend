# Tasks: Split MINIO_ENDPOINT into an internal dial target and a public signing origin

## 0. Setup: Create Fix Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create branch `fix/split-minio-internal-and-public-endpoints` from `main`
- [x] 0.2 Verify branch creation and current branch status (`git branch --show-current`)

## 1. Config: Decouple the Local Environment (Immediate Unblock - NOT the fix)

- [x] 1.1 Set `MINIO_ENDPOINT=127.0.0.1` in `.env` (host-run internal target; MinIO publishes `0.0.0.0:9000`)
- [x] 1.2 Set `MINIO_ENDPOINT=127.0.0.1` in `gtk-companies/gtk-acme/.env` and delete the stale `# host LAN IP ...` comment that conflated the two roles
- [x] 1.3 Set `MINIO_PUBLIC_ENDPOINT=192.168.10.30` in both files (stopgap: current lease, marked for replacement by a DHCP reservation or domain)
- [x] 1.4 Do NOT restart the backend in this step. With the split not yet implemented, a restart would make uploads succeed while signing every photo URL for `127.0.0.1`, converting a loud outage into a silent one. The restart happens in step 5, after the code lands.
- [x] 1.5 Record the measured evidence: host is `192.168.10.30/24` on `wlp2s0` (dynamic DHCP lease), `192.168.10.26:9000` unreachable, `192.168.10.30:9000` and `127.0.0.1:9000` open, `minio-acme` healthy with no `MINIO_REGION` set (so `us-east-1`).

## 2. Backend: Endpoint Split (TDD)

- [x] 2.1 Write failing tests in `tests/test_minio_endpoints.py`: presigned URL host equals `MINIO_PUBLIC_ENDPOINT` while the internal endpoint is unreachable
- [x] 2.2 Write failing tests: `MINIO_PUBLIC_ENDPOINT` unset falls back to `MINIO_ENDPOINT`/`MINIO_PORT`/`MINIO_SECURE`
- [x] 2.3 Write failing tests: `MINIO_PUBLIC_PORT` / `MINIO_PUBLIC_SECURE` override the internal port and scheme (VPS case: `media.example.com:443` TLS public, `minio-acme:9000` plain internal)
- [x] 2.4 Add `minio_public_endpoint`, `minio_public_port`, `minio_public_secure`, `minio_region` to `app/core/settings.py`, with a resolved public origin that falls back to the internal values
- [x] 2.5 Implement `get_minio_client()` (internal) and `get_presigned_client()` (public) in `app/core/storage.py`; both constructed with the explicit `region`
- [x] 2.6 Rewrite `get_presigned_url()` to use the public client
- [x] 2.7 Run the new tests and confirm they pass

## 3. Backend: Presigning Without Network I/O (TDD)

- [x] 3.1 Write a failing test that stubs the MinIO HTTP client, records every request, and asserts `get_presigned_url()` issues none — in particular no `GET /{bucket}?location=` (the `minio/api.py:2259` → `_get_region` path)
- [x] 3.2 Write a failing test that the same stub is never asked for a location on `put_object` / `bucket_exists` either
- [x] 3.3 Construct both clients with `region=settings.minio_region` so `_get_region` returns `_base_url.region` (minio/api.py:483)
- [x] 3.4 Run the tests and confirm they pass

## 4. Backend: Fail Fast and Domain Errors (TDD)

- [x] 4.1 Write failing tests: `StorageUnavailableError` raised for `EHOSTUNREACH` (113), `ECONNREFUSED` (111), `ENETUNREACH` (101) and socket timeout, each naming the configured endpoint
- [x] 4.2 Write a failing test that an `S3Error` (for example `AccessDenied`, `NoSuchBucket`) propagates unchanged
- [x] 4.3 Write a failing test that `ensure_bucket` is not called per upload, and that a failed memoized probe does not poison a later successful upload
- [x] 4.4 Implement `StorageUnavailableError` and a single transport-error translation point in `app/core/storage.py`
- [x] 4.5 Replace the per-upload `ensure_bucket()` with a memoized `ensure_storage_ready()` and wire it into the FastAPI lifespan so an unreachable store aborts startup with one actionable message
- [x] 4.6 Run the tests and confirm they pass

## 5. Backend: Restart and Verify the Real Service

- [x] 5.1 Restart the backend (`uvicorn app.main:app --reload`) and confirm the startup probe succeeds and logs the internal endpoint
- [x] 5.2 Confirm uploads no longer emit `NewConnectionError` or `?location=` retries for the internal dial path
- [x] 5.3 Confirm the process is listening and the API answers

## 6. Backend: Review and Update Existing Unit Tests (MANDATORY)

- [x] 6.1 Review `tests/test_uploads.py`, `tests/test_worksheets.py`, `tests/test_maintenances.py` and `tests/conftest.py` for tests that call `get_minio_client`, `ensure_bucket` or `get_presigned_url` directly, and update them to the new seams
- [x] 6.2 Confirm the startup probe does not attempt real network I/O under `TestClient` (the conftest suite must stay hermetic and offline)
- [x] 6.3 Confirm `tests/test_deploy_assets.py` assertions about `.env.example` still hold after the documentation rewrite in step 9
- [x] 6.4 Run the targeted test files and confirm no regressions

## 7. Backend: Run Unit Tests and Verify Database State (MANDATORY)

- [x] 7.1 Capture the pre-test database baseline (counts for `tickets`, `maintenances`, `worksheets`, `photos`, `upload_sessions`)
- [x] 7.2 Run targeted tests: `pytest tests/test_minio_endpoints.py tests/test_uploads.py -v`
- [x] 7.3 Run the full suite: `pytest -v --cov=app --cov-report=term-missing` (minimum 80%)
- [x] 7.4 Verify the post-test database state matches the baseline; restore if it does not
- [x] 7.5 Create report `openspec/changes/split-minio-internal-and-public-endpoints/specs/minio-endpoint-split/reports/2026-09-29-step-7-unit-test-and-db-verification.md` (AGENT MUST EXECUTE)

## 8. Backend: Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 8.1 Authenticate and obtain a JWT token
- [x] 8.2 `POST /uploads/init` + chunk `PUT` + `POST /uploads/complete` with a real photo and assert the upload succeeds against the internal endpoint
- [x] 8.3 Assert the presigned `photo_url` in the response has host `192.168.10.30` (not `127.0.0.1`, not `192.168.10.26`)
- [x] 8.4 `GET` that presigned URL from the host and assert `200` with the exact bytes uploaded (proves the signature is valid for the public origin)
- [x] 8.5 Error case: point `MINIO_ENDPOINT` at an unreachable address, restart, assert startup aborts with one actionable message naming the endpoint, then restore
- [x] 8.6 Error case: assert an upload against an unreachable store returns the domain error, not a urllib3 traceback
- [x] 8.7 Verify database state matches the pre-test state and remove the test objects

## 9. Documentation (MANDATORY)

- [x] 9.1 Replace the conflation note in `.env.example:50` with the two-variable contract, the LAN/host/Docker values, and the rule that a presigned URL is never rewritten
- [x] 9.2 Update `docs/development_guide.md`: drop the hardcoded `MINIO_ENDPOINT=192.168.10.26`
- [x] 9.3 Update `docs/deployment-guide.md`: document the split, the region pinning, and mark `TICKET-012` resolved in the known-defects table
- [x] 9.4 Add `docs/post-mortems/2026-09-29-minio-endpoint-lease-outage.md` (timeline, contributing factors, why it worked before, why no commit caused it, action items)
- [x] 9.5 Add a learned lesson to `docs/learned-lessons.md` cross-referencing mobile lessons 61/62
- [x] 9.6 Add `MINIO_PUBLIC_ENDPOINT` / `MINIO_REGION` to the deploy runbook environment gate

## 10. Follow-up (Not This Change)

- [ ] 10.1 Replace `MINIO_PUBLIC_ENDPOINT=192.168.10.30` with a DHCP reservation or an internal domain (`media.<domain>`) so a lease rotation can never take photo loading down again
- [ ] 10.2 Remove the archived pre-proposal `openspec/pre_propossals/TICKET-012-*.md` once archived
- [ ] 10.3 Re-check the preflight script in `deploy/` for the new variables
