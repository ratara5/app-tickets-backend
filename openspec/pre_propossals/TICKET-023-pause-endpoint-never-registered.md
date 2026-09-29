# Feature: the maintenance pause endpoint is documented but was never registered

## Metadata

- **Summary**: `PauseRequest` is imported and the design is written down in a comment, but no pause route or service function exists, so `PATCH /maintenances/{maintenance_id}/pause` returns 404 and pausing a maintenance is impossible
- **Issue Type**: Feature Gap
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: backend, api, maintenance, gap
- **Owner**: ratara5
- **Review date**: 2027-01-27, aligned with TICKET-018

## Description

`app/api/routes/tickets.py:87-88` carries a long comment explaining that the pause
endpoint "is now in routes/maintenances.py because it's more related to maintenance
than ticket", and that pausing a maintenance must also drive the ticket to paused.
`app/api/routes/maintenances.py:12` imports `PauseRequest` for exactly that purpose.

Neither the route nor a service function was ever written. Registering the routes
the app actually exposes confirms it:

```
GET          /maintenances
GET          /maintenances/by-ticket/{ticket_id}
GET          /maintenances/{maintenance_id}
POST         /maintenances
PATCH        /maintenances/{maintenance_id}
DELETE       /maintenances/{maintenance_id}/photos/{photo_id}
POST         /maintenances/{maintenance_id}/sign
DELETE       /maintenances/{maintenance_id}
GET          /maintenances/{maintenance_id}/worksheet
POST         /maintenances/{maintenance_id}/worksheet/generate-pdf
PATCH        /maintenances/{maintenance_id}/worksheet
```

There is no `/pause`. `grep` for `pause` in `maintenance_service.py` and
`maintenance_repo.py` finds only the pause-row reconciliation that runs on the
ordinary save path (`replace_maintenance_pauses`), which decides whether a save is
PAUSED or CLOSED. It is a different concern from a dedicated pause endpoint.

So the two tests that cover pausing have been red against a 404 all along, and the
red was easy to misread as an environmental problem.

## Impact

A maintenance cannot be paused on its own. Pausing is only reachable as a side
effect of a worksheet save that introduces a new pause row, which is not the same
contract: it cannot pause without editing the worksheet, and it cannot be expressed
as "pause now".

## Requirements

1. `PATCH /maintenances/{maintenance_id}/pause` accepts a `PauseRequest` body and
   returns the maintenance item.
2. The maintenance transitions to `PAUSED` and its owning ticket is driven to its
   paused status in the same commit, per the design note in `tickets.py:88`.
3. Pausing validates the maintenance status rather than the ticket status, since
   the pause belongs to the maintenance.
4. Pausing an already-paused maintenance is idempotent, not a 409.
5. The owner is authorised; a non-owner gets 403 and an absent id gets 404.
6. Unpausing or resuming is a separate concern and out of scope here.

## Resolution

Recorded rather than implemented: this is a missing feature, not a regression, and
it was found while closing TICKET-005. The two affected tests are marked
`pytest.mark.xfail(strict=True)` in `tests/test_maintenances.py` so the suite is
green while the gap is tracked. Strict, so building the endpoint turns them back
into real tests that must pass. The markers come off in the commit that adds the
route.
