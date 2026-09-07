# Spec: ticket-signed-status

## ADDED Requirements

### Requirement: Ticket state machine supports terminal SIGNED status

The ticket status enum SHALL include a `SIGNED` value ordered immediately after `CLOSED`. `SIGNED` SHALL be a terminal state: the only legal incoming transition is `CLOSED → SIGNED`, and `SIGNED` SHALL have no outgoing transitions.

#### Scenario: Enum exposes SIGNED after CLOSED
- **WHEN** the `TicketStatus` enum is defined in `app/schemas/ticket.py`
- **THEN** it SHALL contain `signed = "SIGNED"` and the enum SHALL list `signed` right after `closed`

#### Scenario: Transition map allows CLOSED to SIGNED
- **WHEN** a ticket with status `CLOSED` tries to transition to `SIGNED`
- **THEN** the transition SHALL be accepted by the state machine (`VALID_TRANSITIONS`)

#### Scenario: Transition map blocks SIGNED outgoing transitions
- **WHEN** a ticket with status `SIGNED` tries to transition to any other status
- **THEN** the state machine SHALL reject the transition

#### Scenario: Transition map blocks SIGNED from other states
- **WHEN** a ticket that is not `CLOSED` (e.g., `OPEN`, `IN PROGRESS`, `PAUSED`, `CANCELLED`) tries to transition to `SIGNED`
- **THEN** the state machine SHALL reject the transition (422)

### Requirement: Sign action marks a closed maintenance as signed

The system SHALL provide an endpoint `POST /maintenances/{maintenance_id}/sign` that transitions the owner ticket from `CLOSED` to `SIGNED`. The action SHALL require the worksheet PDF to already be generated and SHALL be idempotent for already-signed tickets.

#### Scenario: Sign a closed maintenance with a generated PDF
- **WHEN** a technician posts to `POST /maintenances/{maintenance_id}/sign` for a maintenance whose ticket is `CLOSED` and whose worksheet has a generated PDF (`closed == True`)
- **THEN** the ticket status SHALL become `SIGNED` and the response SHALL return the updated maintenance including `ticket_status: "SIGNED"` with status 200

#### Scenario: Sign fails when ticket is not closed
- **WHEN** a user posts to `POST /maintenances/{maintenance_id}/sign` for a maintenance whose ticket is not `CLOSED` (and not already `SIGNED`)
- **THEN** the system SHALL return 422 with a message explaining the invalid transition

#### Scenario: Sign fails when worksheet PDF has not been generated
- **WHEN** a user posts to `POST /maintenances/{maintenance_id}/sign` for a maintenance whose ticket is `CLOSED` but whose worksheet has no generated PDF
- **THEN** the system SHALL return 409 explaining that the worksheet must be generated before signing

#### Scenario: Sign is idempotent for already signed tickets
- **WHEN** a user posts to `POST /maintenances/{maintenance_id}/sign` for a maintenance whose ticket is already `SIGNED`
- **THEN** the system SHALL return 200 with the current maintenance state (including `ticket_status: "SIGNED"`) without erroring

#### Scenario: Sign enforces ownership
- **WHEN** a user without ownership (and not a director) posts to `POST /maintenances/{maintenance_id}/sign` for another technician's maintenance
- **THEN** the system SHALL return 403 Forbidden

#### Scenario: Sign fails for a missing maintenance
- **WHEN** a user posts to `POST /maintenances/{sign}` for a non-existent `maintenance_id`
- **THEN** the system SHALL return 404 Not Found

### Requirement: Maintenance responses include the sticker status

Every maintenance item returned by the API SHALL include a `ticket_status` field with the current status of its owner ticket.

#### Scenario: Maintenance list includes ticket_status
- **WHEN** a user lists maintenances via the maintenances endpoint
- **THEN** every maintenance item SHALL include `ticket_status` reflecting its owner ticket's current status

#### Scenario: Maintenance item reflects SIGNED status
- **WHEN** a maintenance's owner ticket has been signed
- **THEN** the serialized maintenance item SHALL include `ticket_status: "SIGNED"`