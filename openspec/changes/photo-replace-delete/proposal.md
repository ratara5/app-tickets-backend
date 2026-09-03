## Why

The Mobile app can add a mandatory `initial_photo` and a list of `photos` to a maintenance, but there is no way to **delete** an already-persisted photo and no way to **replace (upsert)** a photo in the `photos` list. Technicians therefore cannot correct or remove stored photos, leaving stale objects in MinIO. The `initial_photo` replace backend logic and the MinIO `delete_object` helper are already present in the working tree (the backend already accepts `initial_photo_action` and deletes the old MinIO object on `replace`); this change completes the surface (photo delete + photo replace), formalizes the contract in the canonical API spec, and ships tests.

## What Changes

- **Expose the `initial_photo_action` field in the canonical API spec** — the routes already accept it (`keep`/`replace`/`clear`) but the spec was not regenerated; document it via `docs/api-spec.yml`/`.json`, exposing `keep` | `replace` only (`clear` stays server-side). On `replace`, the backend deletes the previous MinIO object and stores the new one. The mandatory `initial_photo` is **upsertable (replace)** but not deletable.
- **Add photo delete** — `DELETE /maintenances/{maintenance_id}/photos/{photo_id}`: removes the photo's MinIO object and DB row, returning the updated maintenance.
- **Add photo replace (upsert)** — `UploadInitRequest` gains an optional `replaces_photo_id`; on `/uploads/complete` the backend uploads the new object/row and then deletes the replaced photo's MinIO object and DB row (delete-old-plus-add-new, mirroring the `initial_photo` replace pattern).
- **Ownership + validation**: replace/delete operations validate maintenance ownership (same `assert_ownership` rule) and that the photo belongs to the given maintenance. All additions are optional and backward-compatible.
- **Sync `docs/api-spec.yml` / `docs/api-spec.json`** (and `docs/data-model.md` if the schema changes) so the Mobile project consumes the new contract.

## Capabilities

### New Capabilities
- `photo-replace-delete`: Backend support for replacing (upserting) the mandatory `initial_photo`, and inserting (replacing) or deleting maintenance `photos` via delete-old-plus-add-new semantics on MinIO and the photos DB table.

### Modified Capabilities
<!-- No existing backend main specs are created yet. -->

## Impact

- `app/api/routes/maintenances.py` — `initial_photo_action` already present on update/pause; add `DELETE /maintenances/{maintenance_id}/photos/{photo_id}`.
- `app/services/maintenance_service.py` — `initial_photo_action` replace + old-photo cleanup already present; add a photo-delete service (delete MinIO object + DB row).
- `app/core/storage.py` — `delete_object` already present (reused by photo delete/replace).
- `app/schemas/upload.py` — add optional `replaces_photo_id` to `UploadInitRequest`.
- `app/services/upload_service.py` — on `/uploads/complete`, when `replaces_photo_id` is set, delete the replaced photo's object + row after persistence.
- `app/repositories/photo_repo.py` — add `get_photo` / `delete_photo` (by `photo_id` + `maintenance_id`).
- `alembic/versions/` — new migration aligning `photos.maintenance_id` (Integer) to `maintenances.maintenance_id` (Uuid) so delete/replace scoping queries match column types.
- `docs/api-spec.yml` / `docs/api-spec.json` — expose `initial_photo_action` (`keep` | `replace`), new photo delete endpoint, and `replaces_photo_id`.
- `tests/` — tests for `initial_photo_action` replace, photo delete, and photo replace.
- Mobile (separate repo): consumes the updated contract via `docs/api-spec.json`.
