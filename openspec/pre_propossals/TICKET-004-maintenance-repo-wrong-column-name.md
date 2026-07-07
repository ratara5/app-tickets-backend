# Bug: get_maintenance_by_id uses wrong column name

## Metadata

- **Summary**: `get_maintenance_by_id` references non-existent column `Maintenance.id_maintenance`
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, api, repository

## Description

In `app/repositories/maintenance_repo.py:70`, the `get_maintenance_by_id` method uses:

```python
query.filter(Maintenance.id_maintenance == maintenance_id)
```

But the column is named `maintenance_id` (defined in `app/models/maintenance.py:14`), not `id_maintenance`.

Furthermore, the filter result is not assigned back to `query`, so the filter has no effect. The line should be:

```python
query = query.filter(Maintenance.maintenance_id == maintenance_id)
```

**Impact:** GET /maintenances/{id} returns the first maintenance regardless of the requested ID (incorrect data), and may fail with AttributeError.

## Reproduction

```python
response = client.get("/maintenances/{uuid}", headers=auth_headers)
# → 500 Internal Server Error
```
