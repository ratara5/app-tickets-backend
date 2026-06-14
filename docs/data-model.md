# Data Model Documentation

This document describes the data model for the Field Service Management (FSM) / Tickets application, including entity descriptions, field definitions, relationships, and an entity-relationship diagram.

The database name is `db_gestiket_acme` running on PostgreSQL 16.

## Model Descriptions

### 1. fsm_users
Represents system users who can authenticate and perform actions.

**Fields:**
- `user_id`: Unique identifier for the user (Primary Key, SERIAL)
- `email`: User's unique email address (max 150, UNIQUE)
- `user_name`: User's display name (max 50)
- `passwd`: Password hash (max 255, bcrypt)
- `user_role`: Role name (`admin`, `technician`, etc.) (max 50)
- `photo_path`: MinIO object path for user photo (optional, max 500)
- `created_at`: Account creation timestamp (auto)

**Relationships:**
- `technician`: One-to-one relationship with Technician model

### 2. technicians
Represents technical staff linked to user accounts.

**Fields:**
- `technician_id`: Unique identifier (Primary Key, SERIAL)
- `user_id`: Foreign key referencing fsm_users (UNIQUE)

**Relationships:**
- `user`: Many-to-one relationship with FSMUser
- `tickets`: One-to-many relationship with Ticket (assigned)
- `maintenances`: One-to-many through MaintenanceTechnician

### 3. markets
Represents partner/derived markets where service is provided.

**Fields:**
- `market_id`: Unique identifier (Primary Key, INT)
- `market_name`: Market name
- `city`: City location
- `transport_cost`: Transport cost value (NUMERIC 8,2)

**Relationships:**
- `tickets`: One-to-many relationship with Ticket

### 4. equipments
Represents equipment/product types that can be serviced.

**Fields:**
- `equipment_id`: Unique identifier (Primary Key, INT)
- `equipment_name`: Equipment name

**Relationships:**
- `tickets`: One-to-many relationship with Ticket

### 5. uom
Units of measure catalog.

**Fields:**
- `unit`: Unit code (Primary Key, VARCHAR)
- `magnitude`: Physical magnitude (e.g., weight, volume)
- `uom_description`: Detailed description
- `ref_unit`: Reference unit (self-referencing FK)
- `factor_conversion`: Conversion factor to reference unit (NUMERIC 5,2)

**Relationships:**
- `spares`: One-to-many relationship with Spare

### 6. spares
Inventory of spare parts and consumables.

**Fields:**
- `spare_id`: Unique identifier (Primary Key, SERIAL)
- `spare_name`: Spare part name
- `unit`: Unit of measure (FK to uom)
- `price`: Unit price (NUMERIC 10,2)

**Relationships:**
- `uom`: Many-to-one relationship with UOM
- `maintenances`: One-to-many through MaintenanceSpare

### 7. labsdls
Labor schedules — defines hourly rates for different labor types.

**Fields:**
- `labsdl_id`: Unique identifier (Primary Key, SERIAL)
- `labsdl_name`: Schedule name
- `labsdl_description`: Description
- `hourly_rate`: Hourly rate value (NUMERIC 8,2)

**Relationships:**
- `maintenances`: One-to-many relationship with Maintenance

### 8. tickets
Core entity representing a service ticket.

**Enums:**
- `priority_type`: `LOW`, `MEDIUM`, `HIGH`
- `status_type`: `OPEN`, `ASSIGNED`, `CANCELLED`, `IN PROGRESS`, `PAUSED`, `CLOSED`

**Fields:**
- `ticket_id`: Unique identifier (Primary Key, INT)
- `priority`: Priority level (enum)
- `market_id`: FK to Market
- `ticket_date`: Ticket creation date
- `equipment_id`: FK to Equipment
- `ticket_description`: Problem description (TEXT)
- `status`: Current status (enum)
- `assigned_to`: FK to Technician (nullable)
- `created_at`: Timestamp (TIMESTAMPTZ, auto)
- `created_by`: FK to fsm_users (VARCHAR)
- `updated_at`: Last update timestamp (TIMESTAMPTZ, nullable)
- `updated_by`: FK to fsm_users (VARCHAR)

**Relationships:**
- `maintenance`: One-to-one relationship with Maintenance
- `market`: Many-to-one relationship with Market
- `equipment`: Many-to-one relationship with Equipment
- `cancellation`: One-to-one relationship with Cancellation
- `technician`: Many-to-one relationship with Technician
- `add_wkd`: One-to-one relationship with AddWkd

### 9. cancellations
Tracks ticket cancellation details.

**Fields:**
- `ticket_id`: FK to Ticket (Primary Key, INT)
- `cancellation_reason`: Cancellation justification (TEXT)
- `created_at`: Timestamp (auto)
- `created_by`: FK to fsm_users (VARCHAR)
- `updated_at`: Last update (nullable)
- `updated_by`: FK to fsm_users (VARCHAR)

**Relationships:**
- `ticket`: Many-to-one relationship with Ticket

### 10. maintenances
Represents actual maintenance work performed for a ticket. Uses UUID v7 as primary key.

**Fields:**
- `maintenance_id`: UUID v7 (Primary Key, auto-generated via uuid6)
- `ticket_id`: FK to Ticket (INT, UNIQUE)
- `maintenance_date`: Date of maintenance
- `maintenance_description`: Work description (TEXT)
- `labsdl_id`: FK to LabSchedule (set server-side from ticket date — weekend/holiday check)
- `initial_photo_path`: MinIO path for initial photo (set server-side from file upload)
- `observations`: Observations (TEXT)
- `created_at`, `updated_at`, `created_by`, `updated_by`: Audit fields

**Relationships:**
- `ticket`: Many-to-one relationship with Ticket
- `pauses`: One-to-many relationship with Pause
- `photos`: One-to-many relationship with Photo
- `worksheet`: One-to-one relationship with Worksheet
- `labsdl`: Many-to-one relationship with Labsdl
- `technicians`: One-to-many through MaintenanceTechnician
- `spares`: One-to-many through MaintenanceSpare

### 11. maintenances_technicians
Join table linking maintenance work to technicians with time tracking.

**Fields:**
- `maintenance_id`: FK to Maintenance (UUID, composite PK)
- `technician_id`: FK to Technician (INT, composite PK)
- `start_hour`: Start time (TIMETZ)
- `end_hour`: End time (TIMETZ)
- Audit fields

### 12. maintenances_spares
Join table linking maintenance work to spare parts used.

**Fields:**
- `maintenance_id`: FK to Maintenance (UUID, composite PK)
- `spare_id`: FK to Spare (INT, composite PK)
- `qty`: Quantity used (NUMERIC 6,2)
- Audit fields

### 13. photos
Photos associated with maintenance work.

**Fields:**
- `photo_id`: Unique identifier (Primary Key, TEXT)
- `maintenance_id`: FK to Maintenance (UUID)
- `photo_path`: MinIO object path (TEXT)
- `processed`: Boolean flag indicating processing state
- Audit fields

### 14. pauses
Tracks pause events during maintenance work.

**Fields:**
- `pause_id`: Unique identifier (Primary Key, TEXT)
- `maintenance_id`: FK to Maintenance (UUID)
- `pause_reason`: Reason for pause (TEXT)
- Audit fields

### 15. adticketswkd
Additional weekend ticket information.

**Fields:**
- `ticket_id`: FK to Ticket (Primary Key, INT)
- `operation_percentage`: Operation percentage (NUMERIC)
- `market_temperature`: Market temperature (NUMERIC)
- `operation_damage`: Boolean flag
- `completed`: Boolean flag
- `observations_wkd`: Weekend observations (TEXT)
- Audit fields

### 16. materials
Materials used during maintenance (non-inventory items).

**Fields:**
- `material_id`: Unique identifier (Primary Key, SERIAL)
- `ticket_id`: FK to Ticket
- `maintenance_id`: FK to Maintenance (UUID)
- `spare_id`: FK to Spare (reset reference)
- `material_description`: Description (TEXT)
- `qty`: Quantity (NUMERIC)
- `price`: Unit price (NUMERIC)

### 17. services
Services performed during maintenance.

**Fields:**
- `service_id`: Unique identifier (Primary Key, SERIAL)
- `ticket_id`: FK to Ticket
- `maintenance_id`: FK to Maintenance (UUID)
- `service_description`: Description (TEXT)
- `qty`: Quantity (NUMERIC)
- `price`: Unit price (NUMERIC)

### 18. uploads_sessions
Tracks chunked file upload sessions for reliable large file transfers.

**Fields:**
- `upload_id`: UUID v7 (Primary Key)
- `user_id`: FK to fsm_users
- `parent_tab`: Source tab identifier (UUID)
- `parent_id`: Parent entity ID (UUID)
- `tab_name`: Tab name (TEXT)
- `col_name`: Column name (TEXT)
- `content_type`: MIME type (TEXT)
- `total_size`: Total file size (INT)
- `total_chunks`: Total chunk count (INT)
- `received_chunks`: Chunks received (INT)
- `expires_at`: Expiration timestamp (TIMESTAMPTZ)
- `completed`: Boolean flag

### 19. worksheets
PDF worksheets/support documents generated for maintenance.

**Fields:**
- `worksheet_id`: Unique identifier (Primary Key, INT)
- `maintenance_id`: FK to Maintenance (UUID, UNIQUE)
- `receiver_name`: Person who received (VARCHAR 150)
- `receiver_doc_id`: ID document number (VARCHAR 50)
- `receiver_position`: Job position (VARCHAR 100)
- `receiver_sap`: SAP code (VARCHAR 50)
- `receiver_signature`: Signature data (TEXT)
- `receiver_signature_timestamp`: Signature timestamp (TIMESTAMPTZ)
- `sheet_number`: Sequential sheet number (VARCHAR 30, UNIQUE)
- `pdf_url`: URL to generated PDF (VARCHAR 100)
- `generated_at`: PDF generation timestamp (TIMESTAMPTZ)
- `closed`: Boolean flag

### 20. preliquidated
Tracks tickets already processed for pre-liquidation.

**Fields:**
- `ticket_id`: FK to Ticket (Primary Key, INT)
- `timestamp_write_form`: Form write timestamp (TIMESTAMPTZ)

### 21. hollidays
Holidays calendar (note: the project uses the `holidays` Python package as primary source).

**Fields:**
- `holliday_date`: Date (Primary Key, DATE)
- `title`: Holiday name (TEXT)

## Entity Relationship Diagram

```mermaid
erDiagram
    fsm_users {
        int user_id PK
        string email UK
        string user_name
        string passwd
        string user_role
        string photo_path
        datetime created_at
    }
    technicians {
        int technician_id PK
        int user_id FK UK
    }
    markets {
        int market_id PK
        string market_name
        string city
        numeric transport_cost
    }
    equipments {
        int equipment_id PK
        string equipment_name
    }
    uom {
        string unit PK
        string magnitude
        text uom_description
        string ref_unit FK
        numeric factor_conversion
    }
    spares {
        int spare_id PK
        string spare_name
        string unit FK
        numeric price
    }
    labsdls {
        int labsdl_id PK
        string labsdl_name
        string labsdl_description
        numeric hourly_rate
    }
    tickets {
        int ticket_id PK
        string priority
        int market_id FK
        date ticket_date
        int equipment_id FK
        text ticket_description
        string status
        int assigned_to FK
        datetime created_at
        int created_by FK
        datetime updated_at
        int updated_by FK
    }
    cancellations {
        int ticket_id PK FK
        text cancellation_reason
        datetime created_at
        int created_by FK
        datetime updated_at
        int updated_by FK
    }
    maintenances {
        uuid maintenance_id PK
        int ticket_id FK UK
        date maintenance_date
        text maintenance_description
        int labsdl_id FK
        string initial_photo_path
        text observations
        datetime created_at
        int created_by FK
        datetime updated_at
        int updated_by FK
    }
    maintenances_technicians {
        uuid maintenance_id PK FK
        int technician_id PK FK
        time start_hour
        time end_hour
        datetime created_at
        int created_by FK
    }
    maintenances_spares {
        uuid maintenance_id PK FK
        int spare_id PK FK
        numeric qty
        datetime created_at
        int created_by FK
    }
    photos {
        text photo_id PK
        uuid maintenance_id FK
        text photo_path
        boolean processed
        datetime created_at
        int created_by FK
    }
    pauses {
        text pause_id PK
        uuid maintenance_id FK
        text pause_reason
        datetime created_at
        int created_by FK
    }
    adticketswkd {
        int ticket_id PK FK
        numeric operation_percentage
        numeric market_temperature
        boolean operation_damage
        boolean completed
        text observations_wkd
        datetime created_at
        int created_by FK
    }
    materials {
        int material_id PK
        int ticket_id FK
        uuid maintenance_id FK
        int spare_id FK
        text material_description
        numeric qty
        numeric price
    }
    services {
        int service_id PK
        int ticket_id FK
        uuid maintenance_id FK
        text service_description
        numeric qty
        numeric price
    }
    uploads_sessions {
        uuid upload_id PK
        int user_id FK
        uuid parent_tab
        uuid parent_id
        text tab_name
        text col_name
        text content_type
        int total_size
        int total_chunks
        int received_chunks
        datetime expires_at
        boolean completed
    }
    worksheets {
        int worksheet_id PK
        uuid maintenance_id FK UK
        varchar receiver_name
        varchar receiver_doc_id
        varchar receiver_position
        varchar receiver_sap
        text receiver_signature
        datetime receiver_signature_timestamp
        varchar sheet_number UK
        varchar pdf_url
        datetime generated_at
        boolean closed
    }
    preliquidated {
        int ticket_id PK FK
        datetime timestamp_write_form
    }
    hollidays {
        date holliday_date PK
        text title
    }

    fsm_users ||--o| technicians : "has"
    fsm_users ||--o{ tickets : "creates"
    technicians ||--o{ tickets : "assigned_to"
    technicians ||--o{ maintenances_technicians : "works_on"

    markets ||--o{ tickets : "located_in"
    equipments ||--o{ tickets : "equipment"
    uom ||--o{ spares : "measures"
    labsdls ||--o{ maintenances : "labor_rate"

    tickets ||--o| cancellations : "cancelled_by"
    tickets ||--o| maintenances : "has"
    tickets ||--o| adticketswkd : "weekend_data"
    tickets ||--o| preliquidated : "preliquidated"

    maintenances ||--o{ maintenances_technicians : "assigned"
    maintenances ||--o{ maintenances_spares : "uses"
    maintenances ||--o{ photos : "photos"
    maintenances ||--o{ pauses : "pauses"
    maintenances ||--o| worksheets : "document"

    spares ||--o{ maintenances_spares : "used_in"
    spares ||--o{ materials : "catalog_reference"
```

## Key Design Principles

1. **Audit Trail**: All transactional tables include `AuditMixin` with `created_at`, `updated_at`, `created_by`, `updated_by` and relationships to `fsm_users`.

2. **UUID v7 for Distributed IDs**: The `maintenances` table uses `uuid6.uuid7()` as primary key, enabling distributed/offline ID generation without collisions.

3. **Join Tables with Compound Keys**: Many-to-many relationships (maintenances_technicians, maintenances_spares) use compound primary keys with `PrimaryKeyConstraint`.

4. **Soft References**: Some fields reference users via VARCHAR (not FK) in `created_by`/`updated_by` audit fields, allowing flexibility across systems. The actual FK constraint is to `fsm_users(user_id)` via INTEGER.

5. **Chunked Uploads**: The `uploads_sessions` table supports resumable chunked file uploads to handle large files and unreliable connections.

6. **Time Zone Awareness**: Timestamps use `TIMESTAMPTZ` (PostgreSQL timezone-aware type). Conversion to local time is done in the application layer with the configured `TZ_COMPANY`.

7. **Dual Price Tracking**: Materials and services are tracked both as inventory items (spares with unit price) and as free-form entries (materials/services with direct price entry).

## Notes

- All `SERIAL` primary keys are database-managed auto-increment integers
- UUID v7 values are generated client-side via the `uuid6` Python package
- The `AuditMixin` provides consistent `created_at` / `updated_at` / `created_by` / `updated_by` across all transactional tables
- The `uom` table supports self-referencing conversion between units
- File/physical paths reference MinIO object keys, not local filesystem paths
- The `hollidays` table is auxiliary; the `holidays` Python package is the primary data source for holiday calculations
