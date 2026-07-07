# Bug: delete_maintenance calls maintenance_repo.get_ticket_by_id instead of get_maintenance_by_id

## Metadata

- **Summary**: `delete_maintenance` in maintenance_service calls wrong repo method leading to AttributeError
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, service

## Description

In `app/services/maintenance_service.py:164`, `delete_maintenance` calls `maintenance_repo.get_ticket_by_id(db, maintenance_id, current_user)` instead of `maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)`. This causes an `AttributeError` because the maintenance_id (UUID) is passed where a ticket_id (int) is expected.

Also, the result variable is named `maintenance` but assigned from `get_ticket_by_id`, which is misleading.

**Fix:** Change to `maintenance_repo.get_maintenance_by_id(db, maintenance_id, current_user)`.

## Reproduction

```python
response = client.delete("/maintenances/{uuid}", headers=auth_headers)
# → 500 Internal Server Error
```
