# Bug: get_ticket_by_id calls _get_query with wrong number of arguments

## Metadata

- **Summary**: `get_ticket_by_id` passes 3 arguments to `_get_query` which only accepts 2, causing all ticket read/update/delete endpoints to fail
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: Highest
- **Labels**: backend, api, repository

## Description

In `app/repositories/ticket_repo.py:60`, `get_ticket_by_id` calls `_get_query(db, current_user, ticket_id)` with 3 positional arguments. However, `_get_query` at line 67 is defined as `def _get_query(db, current_user)` — it only accepts 2 arguments and has no `ticket_id` parameter.

The `ticket_id` filter should be applied after `_get_query` returns the base query, like:
```python
query = _get_query(db, current_user)
query = query.filter(Ticket.ticket_id == ticket_id)
```

**Impact:** All endpoints that call `get_ticket_by_id` fail with `TypeError`:
- GET /tickets/{ticket_id}
- PATCH /tickets/{ticket_id}/assign
- PATCH /tickets/{ticket_id}/start
- PATCH /tickets/{ticket_id}/cancel
- PATCH /tickets/{ticket_id}/addwkd
- DELETE /tickets/{ticket_id}

## Reproduction

```python
response = client.get("/tickets/1", headers=auth_headers)
# → 500 Internal Server Error (TypeError)
```
