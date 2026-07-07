# Bug: maintenance_repo _get_query chained joinedload is invalid

## Metadata

- **Summary**: Invalid chained joinedload in maintenance_repo causes GET /maintenances to fail
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: Highest
- **Labels**: backend, api, repository

## Description

In `app/repositories/maintenance_repo.py:98-101`, `_get_query` joins extra relationships incorrectly:

```python
joinedload(Maintenance.ticket)
    .joinedload(Ticket.market)
    .joinedload(Ticket.equipment)
    .joinedload(Ticket.cancellation),
```

This chains `.joinedload()` calls on the result of the previous joinedload. However, `.joinedload(Ticket.market)` returns a `Load` object for `Market`, so the subsequent `.joinedload(Ticket.equipment)` tries to find `equipment` on `Market` rather than on `Ticket`.

**Fix:** Each joinedload should be a separate entry in the `.options()` list:

```python
joinedload(Maintenance.ticket).joinedload(Ticket.market),
joinedload(Maintenance.ticket).joinedload(Ticket.equipment),
joinedload(Maintenance.ticket).joinedload(Ticket.cancellation),
```

**Impact:** GET /maintenances fails with `ArgumentError`.

## Reproduction

```python
response = client.get("/maintenances", headers=auth_headers)
# → 500 Internal Server Error (ArgumentError)
```
