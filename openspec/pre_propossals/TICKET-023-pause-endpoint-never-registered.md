# Feature: the maintenance pause endpoint is documented but was never registered

## Metadata

- **Summary**: RESOLVED 2026-09-30 — `PauseRequest` is imported and the design is written down in a comment, but no pause route or service function exists, so `PATCH /maintenances/{maintenance_id}/pause` returns 404 and pausing a maintenance is impossible
- **Issue Type**: Feature Gap
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: backend, api, maintenance, gap
- **Owner**: ratara5
- **Review date**: 2027-01-27, aligned with TICKET-018
- **Status**: Closed 2026-09-30. Route registered, xfail markers removed, requirements 2 and 3 amended (both described a maintenance status that does not exist). See "Resolution".

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
2. A `pauses` row carrying the reason is appended, and the owning ticket is
   driven to `PAUSED` in the same commit, per the design note in `tickets.py:88`.
   **There is no maintenance status.** Neither the live `maintenances` table nor
   the ORM model declares a `status` column, and `alembic check` reports zero
   drift, so the absence is the design, not an oversight. `PAUSED` is therefore
   observable only as the owning ticket's `ticket_status` together with the
   presence of the pause row — never as a `status` field on the response.
3. The pause belongs to the maintenance, so the endpoint is keyed on
   `maintenance_id` and the pausable state is read from the maintenance's owning
   ticket rather than from any client-supplied ticket id: `IN PROGRESS` pauses,
   `PAUSED` is the idempotent retry, and every other ticket status is 422.
4. Pausing an already-paused maintenance is idempotent, not a 409: it returns the
   current state and appends no second pause row.
5. The owner is authorised; a non-owner gets 403 and an absent id gets 404.
6. Unpausing or resuming is a separate concern and out of scope here.

> **Amended 2026-09-30.** Requirements 2 and 3 originally said the *maintenance*
> transitions to `PAUSED` and that pausing "validates the maintenance status
> rather than the ticket status". Both were unimplementable against a schema
> with no maintenance status, and both were wrong rather than merely loose. The
> prose is corrected here; the schema was **not** changed to fit it. One
> consequence: `test_pause_maintenance_success` asserted
> `data["status"] == "PAUSED"`, a field no maintenance response has ever had. It
> was the only maintenance assertion in the suite using `status` instead of
> `ticket_status` (`status` is real only on *ticket* responses, where it was
> copied from) and it had been unreachable behind the 404. It now asserts
> `ticket_status`, matching lines 280, 293, 642, 646, 659 and 662.

## Resolution

### Closed 2026-09-30 — the endpoint exists

`PATCH /maintenances/{maintenance_id}/pause` is registered and the xfail markers
are gone. `PauseRequest` is now a standalone schema rather than a subclass of
`MaintenanceUpdate`, the service function is `pause_maintenance`, and the repo
gained a non-committing `add_pause` so the pause row and the ticket's `PAUSED`
status land in **one** transaction, as requirement 2 demands.

Ten tests cover it (up from two), and each guard was confirmed to bite by
mutating the code and watching the specific test fail:

| Guard | Mutation | Test that failed |
|---|---|---|
| ownership (403) | drop `assert_ownership` | `forbidden_for_other_technician` |
| pausable state (422) | drop `validate_transition` | `rejects_a_closed_ticket` |
| idempotency | drop the already-PAUSED early return | `is_idempotent_when_already_paused`, `appends_to_existing_pauses` |
| server-side `created_at` | fall through to the column default | 4 tests (response validation) |
| `created_by` attribution | drop `current_user` | `persists_the_reason` |
| one commit | `commit=False` → `True` | `commits_the_pause_and_the_status_once` |

Three things found while doing it, none of which the ticket knew about:

1. **`test_pause_maintenance_not_found` was passing for the wrong reason.** It
   used a nil UUID, which every other maintenance route rejects with 422
   because the path binds `UUID7`. It only 404'd because the route did not
   exist at all. It now uses `_ABSENT_UUID7`, the constant the file already
   defined at line 55 for exactly this. This was not an xfail, so nothing would
   have flagged it.
2. **`PauseRequest` was unusable as written.** It subclassed
   `MaintenanceUpdate`, which requires `maintenance_description` and carries the
   `spares`/`technicians`/`pauses` collections that the save path *replaces*.
   Every test body posts `{"pause_reason": ...}` alone, so it would have been a
   422. Worse, inheriting it would have let the endpoint accept — and silently
   discard — the whole mobile form payload.
3. **Auth beats path validation.** `401` is returned before the `422` for a
   non-v7 id, so the unauthorized test is correct as written with a nil UUID.
   Measured, not assumed.

Full suite: 382 passed, 0 xfailed (was 380 passed, 2 xfailed).

Not done, deliberately: resuming/unpausing (requirement 6, still out of scope —
`paused → in_progress` is already reachable as a side effect of the ordinary
save path); any change to the live database; any migration. The
`if ticket is None` guard in `pause_maintenance` is currently **unreachable**,
because `_get_query` inner-joins `Maintenance.ticket` and so can never return a
maintenance whose `ticket_id` is NULL. It is kept as a cheap guard against that
join being loosened to an outer join, and it is not load-bearing.

### Original resolution, for the record

Recorded rather than implemented: this is a missing feature, not a regression, and
it was found while closing TICKET-005. The two affected tests are marked
`pytest.mark.xfail(strict=True)` in `tests/test_maintenances.py` so the suite is
green while the gap is tracked. Strict, so building the endpoint turns them back
into real tests that must pass. The markers come off in the commit that adds the
route.
