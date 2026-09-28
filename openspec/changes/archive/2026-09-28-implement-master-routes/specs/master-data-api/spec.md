## ADDED Requirements

### Requirement: List all technicians
The system SHALL provide a `GET /technicians` endpoint that returns a paginated list of all technicians.

#### Scenario: Successful list
- **WHEN** an authenticated user requests `GET /technicians?page=1&page_size=50`
- **THEN** the system returns HTTP 200 with a JSON array of technician objects, each containing `technician_id`, `user_id`

#### Scenario: Pagination works
- **WHEN** an authenticated user requests `GET /technicians?page=2&page_size=10`
- **THEN** the system returns the second page of 10 technicians, or fewer if less remain

### Requirement: Get technician by ID
The system SHALL provide a `GET /technicians/{technician_id}` endpoint that returns a single technician.

#### Scenario: Successful retrieval
- **WHEN** an authenticated user requests `GET /technicians/1`
- **THEN** the system returns HTTP 200 with a technician object containing `technician_id`, `user_id`

#### Scenario: Not found
- **WHEN** an authenticated user requests `GET /technicians/9999`
- **THEN** the system returns HTTP 404 with an error detail message

### Requirement: List all spares
The system SHALL provide a `GET /spares` endpoint that returns a paginated list of all spare parts.

#### Scenario: Successful list
- **WHEN** an authenticated user requests `GET /spares`
- **THEN** the system returns HTTP 200 with a JSON array of spare objects, each containing `spare_id`, `spare_name`, `unit`, `price`

### Requirement: Get spare by ID
The system SHALL provide a `GET /spares/{spare_id}` endpoint that returns a single spare part.

#### Scenario: Successful retrieval
- **WHEN** an authenticated user requests `GET /spares/1`
- **THEN** the system returns HTTP 200 with a spare object containing `spare_id`, `spare_name`, `unit`, `price`

#### Scenario: Not found
- **WHEN** an authenticated user requests `GET /spares/9999`
- **THEN** the system returns HTTP 404

### Requirement: List all markets
The system SHALL provide a `GET /markets` endpoint that returns a paginated list of all markets.

#### Scenario: Successful list
- **WHEN** an authenticated user requests `GET /markets`
- **THEN** the system returns HTTP 200 with a JSON array of market objects, each containing `market_id`, `market_name`, `city`, `transport_cost`

### Requirement: Get market by ID
The system SHALL provide a `GET /markets/{market_id}` endpoint that returns a single market.

#### Scenario: Successful retrieval
- **WHEN** an authenticated user requests `GET /markets/1`
- **THEN** the system returns HTTP 200 with a market object containing `market_id`, `market_name`, `city`, `transport_cost`

#### Scenario: Not found
- **WHEN** an authenticated user requests `GET /markets/9999`
- **THEN** the system returns HTTP 404

### Requirement: List all equipment
The system SHALL provide a `GET /equipment` endpoint that returns a paginated list of all equipment.

#### Scenario: Successful list
- **WHEN** an authenticated user requests `GET /equipment`
- **THEN** the system returns HTTP 200 with a JSON array of equipment objects, each containing `equipment_id`, `equipment_name`

### Requirement: Get equipment by ID
The system SHALL provide a `GET /equipment/{equipment_id}` endpoint that returns a single equipment.

#### Scenario: Successful retrieval
- **WHEN** an authenticated user requests `GET /equipment/1`
- **THEN** the system returns HTTP 200 with an equipment object containing `equipment_id`, `equipment_name`

#### Scenario: Not found
- **WHEN** an authenticated user requests `GET /equipment/9999`
- **THEN** the system returns HTTP 404

### Requirement: List all labsdls
The system SHALL provide a `GET /labsdls` endpoint that returns a paginated list of all labsdls.

#### Scenario: Successful list
- **WHEN** an authenticated user requests `GET /labsdls`
- **THEN** the system returns HTTP 200 with a JSON array of labsdl objects, each containing `labsdl_id`, `labsdl_name`, `labsdl_description`, `hourly_rate`

### Requirement: Get labsdl by ID
The system SHALL provide a `GET /labsdls/{labsdl_id}` endpoint that returns a single labsdl.

#### Scenario: Successful retrieval
- **WHEN** an authenticated user requests `GET /labsdls/1`
- **THEN** the system returns HTTP 200 with a labsdl object containing `labsdl_id`, `labsdl_name`, `labsdl_description`, `hourly_rate`

#### Scenario: Not found
- **WHEN** an authenticated user requests `GET /labsdls/9999`
- **THEN** the system returns HTTP 404

### Requirement: Authentication required
All master data endpoints SHALL require a valid JWT token via the `Authorization: Bearer <token>` header.

#### Scenario: Missing token
- **WHEN** an unauthenticated request is made to any master data endpoint
- **THEN** the system returns HTTP 403

#### Scenario: Invalid token
- **WHEN** a request with an expired or malformed token is made to any master data endpoint
- **THEN** the system returns HTTP 403

### Requirement: API specification updated
The OpenAPI specification in `docs/api-spec.yml` SHALL include all new master data endpoints with correct request/response schemas.

#### Scenario: Spec validation
- **WHEN** the API spec is loaded by a validator
- **THEN** it MUST include paths for `/technicians`, `/technicians/{technician_id}`, `/spares`, `/spares/{spare_id}`, `/markets`, `/markets/{market_id}`, `/equipment`, `/equipment/{equipment_id}`, `/labsdls`, `/labsdls/{labsdl_id}`

### Requirement: Postman collection updated
The Postman collection SHALL include example requests for all new endpoints in a "Master Data" folder.

#### Scenario: Collection validation
- **WHEN** the Postman collection is opened
- **THEN** it MUST contain a "Master Data" folder with list and get-by-id requests for each model
