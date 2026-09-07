# Add 'SIGNED' Ticket Status after 'CLOSED'

## Why

After a maintenance is closed, the technician signs the generated PDF worksheet in front of the client. Today there is no way to tell a signed maintenance apart from a merely closed one, so the frontend can't show a "signed" state in the maintenances list nor gate the "View PDF" action behind a completed signature. Adding a terminal `SIGNED` status lets the whole lifecycle end at a meaningful, queryable state.

## What Changes

- Add `SIGNED` to the `TicketStatus` enum (`app/schemas/ticket.py`), ordered right after `CLOSED`.
- Add the legal transition `CLOSED → SIGNED` in `VALID_TRANSITIONS` (`app/services/ticket_service.py`); `SIGNED` is terminal (no outgoing transitions).
- Add a new endpoint `POST /maintenances/{maintenance_id}/sign` that marks a closed ticket as signed:
  - Requires the ticket to be `CLOSED` (422 otherwise).
  - **BREAKING**: Requires the worksheet PDF to already be generated (sheet closed). Returns 409 if the PDF does not exist yet.
  - Idempotent: calling again when the ticket is already `SIGNED` returns the current state (200) instead of erroring.
- Expose the owning ticket's status on maintenance items so the maintenances list can render and react to the `SIGNED` state: add `ticket_status` to the maintenance serialization and to `MaintenanceItemResponse` (`app/schemas/maintenance.py`).
- Update the API contract: `docs/api-spec.yml` + `docs/api-spec.json`.
- Update existing tests and add coverage for the new transition, endpoint, and serialization.

## Capabilities

### New Capabilities
- `ticket-signed-status`: Introduces the terminal `SIGNED` ticket status, the `CLOSED → SIGNED` transition, the `POST /maintenances/{maintenance_id}/sign` action, and the `ticket_status` field on maintenance responses.

### Modified Capabilities
- (none — no existing OpenSpec capabilities are defined yet)

## Impact

- **Code**: `app/schemas/ticket.py`, `app/services/ticket_service.py`, `app/services/maintenance_service.py`, `app/schemas/maintenance.py`, new route in `app/api/routes/maintenances.py`.
- **API contract**: new `sign` endpoint ; `MaintenanceItemResponse` gains `ticket_status`.
- **Tests**: `tests/test_tickets.py`, `tests/test_maintenances.py`, `tests/test_worksheets.py` (transition rules, sign endpoint happy/error/idempotent paths, serialization).
- **Docs**: `docs/api-spec.yml`, `docs/api-spec.json`, `docs/data-model.md` if the schema notes list statuses.
- **Frontend (separate project)**: will consume the new status and endpoint; no backend-side frontend work here.
- **No DB migration**: `tickets.status` stays a plain `String` column; `SIGNED` only adds one more valid value.