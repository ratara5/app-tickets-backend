# Design: Add 'SIGNED' Ticket Status after 'CLOSED'

## Context

The ticket lifecycle currently ends at `CLOSED` (`VALID_TRANSITIONS` has no outgoing edges from `CLOSED`). The worksheet PDF is generated per-maintenance via `POST /maintenances/{maintenance_id}/worksheet/generate-pdf`, which requires the ticket to be `CLOSED` and closes the sheet (`worksheet.closed = True`, `pdf_path` set). Signing happens after that, in the field, when the technician gets the PDF signed by the client.

The React Native frontend needs a distinguishable `SIGNED` state so the maintenances list can render it and drive a "Generate PDF" / "View PDF" flow. This backend change provides that state and the action that produces it, keeping the frontend work in the separate project.

Constraints from the codebase:

- `Ticket.status` is a plain `String` column (`app/models/ticket.py`); statuses are only enforced in the enum `TicketStatus` and `VALID_TRANSITIONS`. No DB change required.
- The sign action must follow ownership checks (`assert_ownership`) and the existing layered pattern (route → service → repository).
- Tests must uphold the TDD + 80% coverage standards and the mandatory steps (review tests, run tests, manual curl, docs).

## Goals / Non-Goals

**Goals:**
- Add terminal `SIGNED` status and legalize `CLOSED → SIGNED`.
- Provide an idempotent `sign` endpoint reachable by the frontend after signing a maintenance.
- Expose the owning ticket status on maintenance items so the list UI can display it.
- Keep the API contract (`docs/api-spec.yml`/`.json`) and docs in sync.

**Non-Goals:**
- No frontend work (separate repository and separate proposal).
- No persistence of digital signature data, signature images, or signature timestamps (the worksheet already stores receiver signature fields).
- No new PDF generation logic; `generate-pdf` remains unchanged and is the required prerequisite.
- No change to `TicketStatus` ordering semantics beyond appending `SIGNED` after `CLOSED`.

## Decisions

**Decision 1 — Where the status lives: extend the existing enum + transition map.**
Add `signed = "SIGNED"` to `TicketStatus` and `TicketStatus.closed: [TicketStatus.signed]` in `VALID_TRANSITIONS`; `TicketStatus.signed: []` keeps it terminal.
Rationale: minimal, consistent with the existing state machine. Alternative considered: a separate `is_signed` boolean column — rejected because it splits lifecycle concerns and would require a migration, while the status string already drives every list/filter in the UI.

**Decision 2 — Endpoint shape: `POST /maintenances/{maintenance_id}/sign` (maintenance-scoped).**
Signing is an action on the maintenance (the worksheet PDF of that maintenance gets signed), matching where the frontend lands after signing and where `generate-pdf` already lives. The service resolves the maintenance → its ticket and applies the transition.
Alternative considered: `PATCH /tickets/{ticket_id}/sign`, mirroring `start`/`assign`/`cancel`. Rejected as the primary API because the frontend action is maintenance-oriented and the response (updated maintenance with `ticket_status`) keeps the list item fresh in one round-trip.
Note: `PATCH` verbs are used for existing state transitions; `POST` is reserved for producing the signature event on the maintenance, consistent with `POST .../generate-pdf`.

**Decision 3 — Guards and idempotency.**
- Ticket must be `CLOSED`; otherwise 422 (mirrors `validate_transition` message style).
- The worksheet PDF must already exist (`worksheet.closed == True` and `pdf_path` set); otherwise 409 ("worksheet not generated yet"). This prevents signing before the PDF exists and keeps `generate-pdf` the single gate.
- If the ticket is already `SIGNED`, return 200 with the current state instead of erroring (idempotent retries, mirroring the `start_maintenance` idempotency precedent).
- Ownership enforced via the existing `maintenance_service.assert_ownership`.

**Decision 4 — Expose `ticket_status` on maintenance items.**
Add `ticket_status` to `_serialize_maintenance_item` (from `maintenance.ticket.status`) and to `MaintenanceItemResponse`. The `ticket_id` already exists on the item and `Maintenance.ticket` is a loaded relationship, so this is a cheap read-only addition with no extra query in list paths beyond what ownership already triggers.
Alternative considered: relying on the frontend to join tickets. Rejected: the maintenances list is the natural rendering surface, and coupling the UI to a second fetch adds a flicker/TTL concern.

**Decision 5 — Contract & docs sync.**
Add the `sign` path + `ticket_status` field to `docs/api-spec.yml`; regenerate `docs/api-spec.json` with `scripts/export_openapi.py`; touch `docs/data-model.md` only if it enumerates status values. No Alembic migration (string column, no schema change).

## Risks / Trade-offs

- [`ticket_status` serialization leaks an extra field on every maintenance response] → Accepted: read-only, derived from a relationship already loaded for ownership; negligible payload growth; enables the frontend list feature.
- [Signing without a signature record may look incomplete] → Mitigation: this is intentionally out of scope; the worksheet already captures receiver signature fields, and storing digital signatures is a future capability.
- [`SIGNED` becomes permanently terminal] → Mitigation: matches `CLOSED`/`CANCELLED` today; reopening an already-signed ticket can be designed later as a separate transition if the business needs it.
- [Idempotent 200 on already-`SIGNED` could hide a client bug] → Mitigation: still 422 for non-`CLOSED`/non-`SIGNED` states; the 200 path only triggers for the exact terminal `SIGNED` state.

## Migration Plan

Deploy: backend change only — code + tests + API spec docs. No DB migration, no data backfill (existing `CLOSED` tickets simply remain `CLOSED`; they are signed forward only).

Rollback: revert the enum value, transition, endpoint, and serialization field; existing `SIGNED` rows would then carry an unknown-but-plain-string value (harmless since the column is unconstrained).

## Open Questions

None blocking. Future consideration: whether `SIGNED` should allow re-opening (e.g., `SIGNED → IN PROGRESS`) once PDF corrections are requested.