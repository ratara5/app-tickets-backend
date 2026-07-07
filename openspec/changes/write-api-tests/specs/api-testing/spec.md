## ADDED Requirements

### Requirement: Test factories for all models

The system SHALL provide factory_boy factories for all 16 SQLAlchemy models to enable concise and reusable test data setup.

#### Scenario: All factories create valid model instances

- **WHEN** using any factory's `create()` method
- **THEN** a valid model instance is persisted to the test database with all required fields populated

#### Scenario: Factories produce deterministic defaults

- **WHEN** using a factory without arguments
- **THEN** the created instance SHALL have sensible default values for all fields

#### Scenario: Factories support field overrides

- **WHEN** passing keyword arguments to a factory
- **THEN** those values SHALL override the default values

### Requirement: Ticket API tests

The system SHALL provide API integration tests for all 8 ticket endpoints.

#### Scenario: Create ticket returns 201 with ticket data

- **WHEN** sending a POST /tickets request with valid ticket data and valid auth
- **THEN** the response SHALL have status 201 and contain the created ticket

#### Scenario: Create ticket returns 422 for invalid data

- **WHEN** sending a POST /tickets request with missing required fields
- **THEN** the response SHALL have status 422

#### Scenario: List tickets returns paginated results

- **WHEN** sending a GET /tickets request with valid auth
- **THEN** the response SHALL have status 200 and contain a paginated list of tickets

#### Scenario: Get ticket returns 200 with ticket data

- **WHEN** sending a GET /tickets/{id} request for an existing ticket
- **THEN** the response SHALL have status 200 and contain the ticket

#### Scenario: Get ticket returns 404 for non-existent ticket

- **WHEN** sending a GET /tickets/{id} for a non-existent ticket ID
- **THEN** the response SHALL have status 404

#### Scenario: Assign ticket returns 200 with updated status

- **WHEN** sending a PATCH /tickets/{id}/assign with a valid technician
- **THEN** the response SHALL have status 200 and the ticket's assigned technician SHALL be updated

#### Scenario: Start ticket returns 200 with in-progress status

- **WHEN** sending a PATCH /tickets/{id}/start on an assigned ticket
- **THEN** the response SHALL have status 200 and the ticket status SHALL be in-progress

#### Scenario: Cancel ticket returns 200

- **WHEN** sending a PATCH /tickets/{id}/cancel with a reason
- **THEN** the response SHALL have status 200 and the ticket status SHALL be cancelled

#### Scenario: Add WKD returns 200

- **WHEN** sending a PATCH /tickets/{id}/addwkd with valid weekend data
- **THEN** the response SHALL have status 200

#### Scenario: Delete ticket returns 204

- **WHEN** sending a DELETE /tickets/{id} for an existing ticket
- **THEN** the response SHALL have status 204

#### Scenario: Unauthenticated requests return 401

- **WHEN** sending any request to ticket endpoints without auth headers
- **THEN** the response SHALL have status 401

#### Scenario: Invalid state transition returns 400

- **WHEN** sending a transition request that violates the state machine (e.g., starting an unassigned ticket)
- **THEN** the response SHALL have status 400

### Requirement: Maintenance API tests

The system SHALL provide API integration tests for all 5 maintenance endpoints.

#### Scenario: Create maintenance returns 201

- **WHEN** sending a POST /maintenances request with valid data and valid auth
- **THEN** the response SHALL have status 201 and contain the created maintenance

#### Scenario: List maintenances returns paginated results

- **WHEN** sending a GET /maintenances request with valid auth
- **THEN** the response SHALL have status 200 and contain a paginated list

#### Scenario: Get maintenance returns 200

- **WHEN** sending a GET /maintenances/{id} for an existing maintenance
- **THEN** the response SHALL have status 200 and contain the maintenance

#### Scenario: Update maintenance returns 200

- **WHEN** sending a PATCH /maintenances/{id} with valid update data
- **THEN** the response SHALL have status 200 and the maintenance SHALL be updated

#### Scenario: Pause maintenance returns 200

- **WHEN** sending a PATCH /maintenances/{id}/pause with a reason
- **THEN** the response SHALL have status 200 and the maintenance SHALL be paused

#### Scenario: Delete maintenance returns 204

- **WHEN** sending a DELETE /maintenances/{id} for an existing maintenance
- **THEN** the response SHALL have status 204

#### Scenario: Maintenance endpoints return 401 without auth

- **WHEN** sending any maintenance request without auth headers
- **THEN** the response SHALL have status 401

#### Scenario: Non-existent maintenance returns 404

- **WHEN** sending GET/PATCH/DELETE /maintenances/{id} for a non-existent ID
- **THEN** the response SHALL have status 404

### Requirement: Upload API tests

The system SHALL provide API integration tests for all 4 chunked upload endpoints.

#### Scenario: Init upload returns 201 with upload ID

- **WHEN** sending a POST /uploads/init with valid file metadata
- **THEN** the response SHALL have status 201 and contain upload_id

#### Scenario: Upload chunk returns 200

- **WHEN** sending a POST /uploads/chunk with a valid upload_id and chunk data
- **THEN** the response SHALL have status 200

#### Scenario: Get upload status returns 200

- **WHEN** sending a GET /uploads/status/{upload_id} for an existing upload
- **THEN** the response SHALL have status 200 with chunk count and status

#### Scenario: Complete upload returns 200

- **WHEN** sending a POST /uploads/complete with a valid upload_id after all chunks are uploaded
- **THEN** the response SHALL have status 200

#### Scenario: Upload endpoints return 401 without auth

- **WHEN** sending any upload request without auth headers
- **THEN** the response SHALL have status 401

### Requirement: Worksheet API tests

The system SHALL provide API integration tests for all 3 worksheet endpoints.

#### Scenario: Get or create worksheet returns 200

- **WHEN** sending a GET /maintenances/{id}/worksheet for an existing maintenance
- **THEN** the response SHALL have status 200 with worksheet data

#### Scenario: Update worksheet returns 200

- **WHEN** sending a PATCH /maintenances/{id}/worksheet with valid fields
- **THEN** the response SHALL have status 200 and the worksheet SHALL be updated

#### Scenario: Generate PDF returns 200

- **WHEN** sending a POST /maintenances/{id}/worksheet/generate-pdf
- **THEN** the response SHALL have status 200

#### Scenario: Worksheet endpoints return 401 without auth

- **WHEN** sending any worksheet request without auth headers
- **THEN** the response SHALL have status 401

#### Scenario: Worksheet for non-existent maintenance returns 404

- **WHEN** sending worksheet requests for a non-existent maintenance ID
- **THEN** the response SHALL have status 404
