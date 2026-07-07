# Bug: TicketCreate schema missing market_id and equipment_id fields

## Metadata

- **Summary**: TicketCreate Pydantic schema missing market_id and equipment_id fields, causing POST /tickets to fail with 500
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: Highest
- **Labels**: backend, api, schema

## Description

The `TicketCreate` schema in `app/schemas/ticket.py` only includes `ticket_id`, `ticket_date`, `ticket_description`, `priority`, and `status`. However, `app/repositories/ticket_repo.py:22-23` accesses `data.market_id` and `data.equipment_id` which don't exist on the model.

This causes an `AttributeError: 'TicketCreate' object has no attribute 'market_id'` when creating a ticket.

**Files affected:**
- `app/schemas/ticket.py` — Add `market_id: int` and `equipment_id: int` fields
- Possibly `app/repositories/ticket_repo.py` — verify the field names match

## Reproduction

```python
response = client.post("/tickets", json={
    "ticket_id": "1",
    "ticket_date": "2024-01-01T00:00:00",
    "ticket_description": "Test",
    "priority": "NORMAL",
    "status": "OPEN",
})
# → 500 Internal Server Error (AttributeError)
```
