## Context

The FSM backend (FastAPI + SQLAlchemy + MinIO) manages tickets, maintenance, spares, technicians, and photos. The Mobile app consumes this contract via `docs/api-spec.json`.

Current state:
- The backend already implements the `initial_photo` replace foundation in the working tree:
  - `initial_photo_action` (`keep` / `replace` / `clear`) as a `Form("keep")` field on `PATCH /maintenances/{maintenance_id}` and `/pause`.
  - `delete_object` in `app/core/storage.py` (MinIO removal helper).
  - `update_existing` `replace` behavior: uploads the new object and deletes the previous `initial_photo_path` (best-effort, logged via structlog).
- The canonical API spec (`docs/api-spec.yml` / `.json`) was **not regenerated** to include `initial_photo_action`, so the Mobile project does not know the field exists.
- There is no endpoint to delete a photo in the `photos` list, and no way to replace (upsert) one. `photo_repo` only has `save_photo`.
- `Photo` has `photo_id` (PK), `maintenance_id` (FK), `photo_path` (MinIO path). `PhotoOut` serializes to `{ photo_id, photo_url }`.

This change completes the photo delete/replace surface and formalizes the `initial_photo_action` contract so the Mobile project (sibling change `photo-replace-delete`) can consume it.

## Goals / Non-Goals

**Goals:**
- Make `initial_photo_action` (`keep` | `replace`) part of the canonical API spec on the update (and pause) routes; verify the existing replace behavior deletes the old MinIO object (add tests).
- Add `DELETE /maintenances/{maintenance_id}/photos/{photo_id}` (delete MinIO object + DB row).
- Add optional `replaces_photo_id` to `UploadInitRequest`; on `/uploads/complete` delete the replaced photo's object + row after the new one is persisted (delete-old-plus-add-new).
- Keep ownership (`assert_ownership`) and ticket-status validation on all new operations.
- Keep backward compatibility (all additions optional; `initial_photo_action` defaults to `keep`).
- Update `docs/api-spec.yml` / `.json` and `tests/`.

**Non-Goals:**
- Making the initial photo deletable — `clear` is implemented in the service but is **server-side only**: the public `initial_photo_action` contract exposes `keep`/`replace` for the mandatory field, never `clear`.
- Changing the chunked-upload protocol structure (only adding an optional field).
- Video/PDF delete support (photo-specific now; the delete-old-plus-add-new pattern generalizes later).

## Decisions

### 1. Expose the existing `initial_photo_action` replace in the API spec
The backend already implements the replace logic (route form field, `delete_object`, old-photo cleanup in `update_existing`). The work here is to **regenerate `docs/api-spec.yml`/`.json`** so the field appears in the contract, and to add a test pinning `replace` (delete old + add new). The public contract exposes `keep` | `replace` only; the Mobile project passes `keep`/`replace` for the mandatory field and never `clear`.
- **Alternative considered:** rewriting the existing replace logic — rejected; it is correct and complete; only the spec surface and tests are missing.

### 2. Photo delete endpoint `DELETE /maintenances/{maintenance_id}/photos/{photo_id}`
A new route in `app/api/routes/maintenances.py` delegates to a service method that: (a) loads the maintenance + asserts ownership, (b) loads the photo filtered by `photo_id` AND `maintenance_id` (so a foreign photo 404s), (c) calls `delete_object(photo_path)` on MinIO (best-effort; log on failure), (d) deletes the DB row, and (e) returns the re-serialized maintenance.
- **Alternative considered:** `DELETE /photos/{photo_id}` without the maintenance scoping — rejected; scoping by maintenance_id prevents cross-maintenance deletion and keeps the path owner-bound.

### 3. Photo replace via `replaces_photo_id` on the upload protocol
`UploadInitRequest` gains `replaces_photo_id: Optional[int] = None`, stored on the `UploadSession` row. On `complete_upload`, after the new photo is uploaded and persisted via `dispatch_service`, if `replaces_photo_id` is set the service loads that photo (scoped to the session's `parent_id` maintenance) and deletes its MinIO object + DB row. The old object is deleted **after** the new one succeeds, so a failed upload never loses the old photo.
- **Alternative considered:** a separate `PUT /maintenances/{id}/photos/{photo_id}` replace endpoint — rejected; reusing `/uploads/*` keeps a single upload/progress/retry path.
- **Alternative considered:** delete-old-first — rejected; would risk data loss if the upload fails.

### 4. Ownership + status guards on new paths
Photo delete and replace target a maintenance; both call `assert_ownership` (director bypass) and validate the photo belongs to that maintenance. The initial-photo replace keeps the existing ticket-status guard.
- **Alternative considered:** allowing any authenticated user to delete — rejected; would leak/alter other technicians' data.

### 5. Backward compatibility + spec sync
`replaces_photo_id` is optional; `initial_photo_action` defaults to `keep`; the new route is additive. `docs/api-spec.yml` is regenerated to capture the new form fields and endpoint; `docs/api-spec.json` is re-exported from the running backend so the Mobile project consumes it unchanged.

## Risks / Trade-offs

- **`Photo.maintenance_id` FK is `Integer` but `Maintenance.maintenance_id` is `Uuid`** → this inconsistency is confirmed and SHALL be fixed with an Alembic migration that aligns `photos.maintenance_id` to the same type as `maintenances.maintenance_id`, so the delete/replace scoping queries match the actual column types. The migration is in-scope (Section 6 of tasks).
- **Deleting the MinIO object fails but the DB row deletion succeeds** → a dangling DB row with a missing object. Mitigation: attempt `delete_object` first (log on failure but do not block), delete the row, and expose a cleanup log (`photo_delete_object_failed`) for reconciliation.
- **Replace target removed concurrently** → 404/409 on complete. Mitigation: catch the missing-photo case and treat as no-op-with-warning; the new photo still persists.
- **MinIO is synchronous** → use the existing `ThreadPoolExecutor` pattern already in place for `upload_file`/`delete_object`.

## Migration Plan

The `photos.maintenance_id` FK type mismatch (`Integer` vs `Uuid`) is confirmed and SHALL be fixed with an Alembic migration aligning `photos.maintenance_id` to `maintenances.maintenance_id`. No other schema migration is expected for the endpoint additions. Rollback is a revert of the change's commit plus the migration downgrade. `docs/api-spec.yml`/`.json` are regenerated; the new fields are optional so existing Mobile builds remain compatible.

## Open Questions

- Should `DELETE` return the updated maintenance (200 + `MaintenanceItemResponse`) or 204? → Resolved: return the updated `MaintenanceItemResponse` so the Mobile project can refresh the photos list without a second GET.
- Whether `clear` should remain publicly supported on the update route — Resolved: keep it in the service for API completeness; the Mobile project only sends `keep`/`replace` for the mandatory initial photo.
