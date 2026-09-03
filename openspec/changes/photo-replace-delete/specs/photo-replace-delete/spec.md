## ADDED Requirements

### Requirement: Replace the mandatory initial photo (upsert)
`PATCH /maintenances/{maintenance_id}` SHALL accept an `initial_photo_action` form field. The public contract SHALL expose `keep` or `replace`; `clear` SHALL NOT be exposed to clients (the service may retain a server-side-only `clear` for internal use). When `initial_photo_action` is `replace`, the backend SHALL upload the new `initial_photo_file` and delete the previously stored MinIO object, then persist the new object path. The `initial_photo` is mandatory and therefore upsertable (replace) but SHALL NOT be deletable from the client for the initial-photo field.

#### Scenario: Replace the initial photo
- **WHEN** a client sends `PATCH /maintenances/{maintenance_id}` with `initial_photo_action=replace`, a new `initial_photo_file`, and a valid maintenance update payload
- **THEN** the backend uploads the new object to MinIO, deletes the previous `initial_photo_path` object, and persists the new `initial_photo_path`
- **AND** the response maintenance reflects the new `initial_photo_url`

#### Scenario: Keep the initial photo unchanged
- **WHEN** a client sends `initial_photo_action=keep` with no `initial_photo_file`
- **THEN** the existing `initial_photo_path` and URL are preserved

#### Scenario: Replace on an invalid ticket status
- **WHEN** the associated ticket is not `IN PROGRESS` or `PAUSED`
- **THEN** the update is rejected with `422` and no MinIO object is deleted

### Requirement: Delete a maintenance photo
The backend SHALL expose `DELETE /maintenances/{maintenance_id}/photos/{photo_id}`. It SHALL validate that the photo belongs to the given maintenance and that the requester owns the maintenance, then delete the photo's MinIO object and its DB row. The response SHALL return the updated maintenance (`MaintenanceItemResponse`) without the deleted photo.

#### Scenario: Delete an existing photo
- **WHEN** a client calls `DELETE /maintenances/{maintenance_id}/photos/{photo_id}` for a photo belonging to that maintenance
- **THEN** the backend deletes the photo's MinIO object and DB row
- **AND** the response maintenance's `photos` list no longer contains the photo

#### Scenario: Delete a photo from a different maintenance
- **WHEN** the `photo_id` does not belong to the given `maintenance_id`
- **THEN** the backend rejects with `404` and deletes nothing

#### Scenario: Delete without ownership
- **WHEN** the requester does not own the maintenance (not a director and not the assigned technician)
- **THEN** the backend rejects with `403` and deletes nothing

### Requirement: Replace (upsert) a maintenance photo
`POST /uploads/init` SHALL accept an optional `replaces_photo_id` in `UploadInitRequest`. On `POST /uploads/complete`, after successfully persisting the new photo row and object, the backend SHALL delete the replaced photo's MinIO object and DB row (delete-old-plus-add-new). If the upload fails, the replaced photo SHALL remain intact.

#### Scenario: Replace an existing photo via the upload protocol
- **WHEN** a client starts `/uploads/init` with `replaces_photo_id` set and completes the upload
- **THEN** the new photo object and row are persisted, and the replaced photo's MinIO object and DB row are deleted
- **AND** the maintenance's `photos` list contains the new photo and no longer the replaced one

#### Scenario: Failed replacement leaves the old photo intact
- **WHEN** the upload does not reach `/uploads/complete` successfully
- **THEN** the replaced photo's MinIO object and DB row are NOT deleted
- **AND** the replaced photo remains in the maintenance's `photos` list

#### Scenario: Replace target does not belong to the maintenance
- **WHEN** `replaces_photo_id` references a photo that does not belong to the session's `parent_id` maintenance
- **THEN** `complete` rejects with `422` (or `404`) and deletes nothing

### Requirement: Align photos maintenance foreign key type
The `photos.maintenance_id` column SHALL be aligned by an Alembic migration to the same type as `maintenances.maintenance_id` (`Uuid`) so that photo delete and photo replace scoping queries (`photo.maintenance_id == maintenance_id`) match the actual column types and do not error on a type mismatch.

#### Scenario: Migration aligns photos.maintenance_id
- **WHEN** the Alembic migration for this change is applied
- **THEN** `photos.maintenance_id` has the same type as `maintenances.maintenance_id` (`Uuid`)
- **AND** delete/replace scoping queries against `photo.maintenance_id` succeed without a type mismatch

