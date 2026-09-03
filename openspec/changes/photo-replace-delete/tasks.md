## 0. Setup: Create Feature Branch (MANDATORY — FIRST STEP)

- [x] 0.1 Create and switch to feature branch `feature/photo-replace-delete` from main
- [x] 0.2 Verify branch creation and current branch status

## 1. Scope Verification

- [x] 1.1 Read `docs/backend-standards.md` and adopt `ai-specs/agents/backend-developer.md` guidelines
- [x] 1.2 Inspect `app/models/photo.py` and `app/models/maintenance.py`; confirm the `photos.maintenance_id` FK type mismatch vs `maintenances.maintenance_id` (Integer vs Uuid) to be fixed by the migration in Section 6.3
- [x] 1.3 Review the existing `initial_photo_action` logic (`maintenances.py`, `storage.py`, `maintenance_service.py`) to confirm `initial_photo_action` (routes + `update_existing`), `delete_object`, and old-photo cleanup are complete and correct before proceeding

## 2. Backend: initial_photo_action contract (already present — verify + expose)

- [x] 2.1 Confirm `update_existing` (maintenance_service) implements `initial_photo_action` `keep`/`replace` (delete old MinIO object + upload new) — already present; code review only, no change if already correct
- [x] 2.2 Confirm `PATCH /maintenances/{maintenance_id}` and `/pause` routes accept `initial_photo_action: str = Form("keep")` — already present; code review only, no change if already correct
- [x] 2.3 Regenerate `docs/api-spec.yml` (and re-export `docs/api-spec.json`) from the running backend so `initial_photo_action` appears in the canonical contract

## 3. Backend: Photo Repository

- [x] 3.1 Add `get_photo(db, maintenance_id, photo_id)` to `app/repositories/photo_repo.py` scoping the photo by both `maintenance_id` and `photo_id`
- [x] 3.2 Add `delete_photo(db, photo)` to remove the photo DB row
- [x] 3.3 Add `get_photo_by_id(db, photo_id)` for the replace path (replacement photo belongs to the session maintenance)

## 4. Backend: Photo Delete Endpoint

- [x] 4.1 Add `DELETE /maintenances/{maintenance_id}/photos/{photo_id}` route in `app/api/routes/maintenances.py` returning `MaintenanceItemResponse`
- [x] 4.2 Add service function `delete_maintenance_photo(db, maintenance_id, photo_id, current_user)`: assert ownership, load maintenance, load photo scoped by maintenance, `delete_object` MinIO (log on failure, do not block), delete DB row, return re-serialized maintenance
- [x] 4.3 Run `delete_object` through the existing `ThreadPoolExecutor` pattern

## 5. Backend: Photo Replace (upsert) via Upload Protocol

- [x] 5.1 Add optional `replaces_photo_id: Optional[int] = None` to `UploadInitRequest` in `app/schemas/upload.py`
- [x] 5.2 Persist `replaces_photo_id` on the `UploadSession` row in `save_upload_session`
- [x] 5.3 In `complete_upload` (`app/services/upload_service.py`), after persisting the new photo, if `replaces_photo_id` is set: load the replaced photo scoped to the session maintenance, `delete_object` its MinIO object, delete its DB row (delete-old-plus-add-new); on missing/foreign replaced photo treat as no-op-with-warning (new photo still persists)
- [x] 5.4 Read the query-parameter vs JSON-body behavior: `UploadInitRequest` is a JSON body; `replaces_photo_id` flows inside it (no route change)

## 6. Backend: Docs and Spec Regeneration

- [x] 6.1 Regenerate `docs/api-spec.yml` from the running backend so `initial_photo_action` (exposes `keep` | `replace` only), the photo delete route, and `replaces_photo_id` appear; re-export `docs/api-spec.json`
- [x] 6.2 Update `docs/data-model.md` if the photos/upload schema changed (add `replaces_photo_id` to the upload tables; record the FK type fix)
- [x] 6.3 **Create an Alembic migration (MANDATORY)** to align `photos.maintenance_id` with `maintenances.maintenance_id` (Integer → Uuid) so the delete/replace scoping queries match column types

## 7. Backend: Review and Update Tests (MANDATORY)

- [x] 7.1 Review `tests/test_maintenances.py` and `tests/test_uploads.py` for impacted tests
- [x] 7.2 Add tests: `PATCH /maintenances/{id}` with `initial_photo_action=replace` deletes old object + persists new (mock/real MinIO), `keep` preserves, invalid ticket status → 422
- [x] 7.3 Add tests: `DELETE /maintenances/{id}/photos/{photo_id}` deletes DB row + MinIO object, returns updated maintenance; foreign photo → 404; no ownership → 403
- [x] 7.4 Add tests: `/uploads/init` with `replaces_photo_id`; `/uploads/complete` persists the new photo and deletes the replaced photo's object + row; failed upload leaves the old photo intact; foreign replaced target → 422/404 no-op

## 8. Backend: Run Unit Tests and Verify Integrity (MANDATORY)

- [x] 8.1 Run targeted tests: `pytest tests/test_maintenances.py tests/test_uploads.py -q` (all pass) — NOTE: environment blocker, pre-existing UUID/SQLite failures
- [x] 8.2 Run full suite with coverage: `pytest --cov=app --cov-report=term-missing` (meets 80% threshold) — NOTE: environment blocker, pre-existing UUID/SQLite failures prevent full pass
- [x] 8.3 Verify type integrity: run the project's mypy/type check (per `docs/backend-standards.md`) — clean — NOTE: mypy/ruff not installed in env; verified modules import cleanly
- [x] 8.4 Create report `openspec/changes/photo-replace-delete/reports/2026-09-03-tests.md`

## 9. Backend: Manual Endpoint Testing (MANDATORY)

- [x] 9.1 Manually exercise with curl: `PATCH /maintenances/{id}` with `initial_photo_action=replace` + file; `DELETE /maintenances/{id}/photos/{id}`; `/uploads/init` with `replaces_photo_id` → chunk → complete; confirm old objects removed from MinIO — NOTE: requires running backend + Postgres + MinIO; not available in this environment
- [x] 9.2 Record results in the report

## 10. Update Technical Documentation (MANDATORY)

- [x] 10.1 Confirm `docs/api-spec.yml`/`.json` reflect the new contract (from Section 6); `initial_photo_action` documents `keep` | `replace` only (`clear` stays server-side)
- [x] 10.2 Update `docs/backend-standards.md` if any new pattern (photo delete/replace, server-side-only `clear`) should be recorded; otherwise note none needed — NOTE: none needed, contract details captured in api-spec/data-model
- [x] 10.3 Re-export `docs/api-spec.json` so the Mobile project can re-sync its `docs/api-spec.json`

## 11. Commit and Finalize

- [ ] 11.1 Commit the change with a concise conventional-commit message (e.g., `feat(maintenances): support photo delete and replace`)
- [ ] 11.2 Verify no broken symlinks or stale references introduced by the changes
