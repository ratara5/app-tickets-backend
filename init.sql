-- =========================
-- DATABASE
-- =========================

-- server:postgres-gci -- db receive mails from gm
-- CREATE DATABASE db_gestiket_acme 
-- \c db_gestiket_tecfrio

-- =========================
-- EXTENSIONS
-- =========================

CREATE EXTENSION IF NOT EXISTS pg_uuidv7;

-- =========================
-- MASTER (CATALOGS ARE INCLUDE WITHIN)
-- =========================

CREATE TABLE IF NOT EXISTS fsm_users ( -- user is a reserved word
    user_id    SERIAL PRIMARY KEY, -- as user is not exposed, SERIAL is enough. In other case, UUID
    email VARCHAR(150) NOT NULL UNIQUE,
    user_name VARCHAR(50) NOT NULL , -- name is a reserved word
    passwd   VARCHAR(255) NOT NULL,
    user_role VARCHAR(50) NOT NULL,
    photo_path VARCHAR(500), -- before 'archivo_foto', is a minio path
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS technicians (
    technician_id SERIAL PRIMARY KEY, --before id_tecnico
    user_id INT NOT NULL UNIQUE,
    -- email VARCHAR UNIQUE, -- redundant, now in fsm_users
    -- technician_name VARCHAR, -- redundant, now in fsm_users
    -- more fields...

    FOREIGN KEY (user_id) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS markets ( -- partners derivate
    market_id INT PRIMARY KEY,
    market_name VARCHAR,  -- without (  ) because existents records have unknown length
    city VARCHAR,
    transport_cost NUMERIC(8, 2)
);

CREATE TABLE IF NOT EXISTS equipments ( -- products derivate
    equipment_id INT PRIMARY KEY,
    equipment_name VARCHAR
);

CREATE TABLE IF NOT EXISTS uom (
	unit VARCHAR PRIMARY KEY,
	magnitude VARCHAR,
	uom_description TEXT,
	ref_unit VARCHAR,
	factor_conversion NUMERIC(5, 2),
	
	FOREIGN KEY (ref_unit) REFERENCES uom(unit)
);

CREATE TABLE IF NOT EXISTS spares ( -- products derivate
    spare_id SERIAL PRIMARY KEY,
    spare_name VARCHAR,
    unit VARCHAR,
    price NUMERIC(10, 2),

    FOREIGN KEY (unit) REFERENCES uom(unit)
);

CREATE TABLE IF NOT EXISTS labsdls ( -- laboral schedules
    labsdl_id SERIAL PRIMARY KEY,
    labsdl_name VARCHAR,
    labsdl_description VARCHAR,
    hourly_rate NUMERIC(8, 2)
);

-- =========================
-- TYPES
-- =========================

DO $$ BEGIN
    CREATE TYPE priority_type AS ENUM ('LOW', 'MEDIUM', 'HIGH'); --  these types could be created and managed in sqlalchemy too
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE status_type AS ENUM ('OPEN', 'ASSIGNED', 'CANCELLED', 'IN PROGRESS', 'PAUSED', 'CLOSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =========================
-- TRANSACTIONALS
-- =========================

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id INT PRIMARY KEY,
    priority priority_type,
    market_id INT,
    ticket_date DATE,
    equipment_id INT,
    ticket_description TEXT,
    status status_type,
    assigned_to INT,

    created_at TIMESTAMPTZ DEFAULT NOW(), -- Only works if other apps write in DB without pass throughout ORM. --Convert to UTC on save. Reconvert at timezone which must be include in query
    created_by VARCHAR,
    updated_at TIMESTAMPTZ NULL,
    updated_by VARCHAR,

    FOREIGN KEY (market_id) REFERENCES markets(market_id),
    FOREIGN KEY (equipment_id) REFERENCES equipments(equipment_id),
    FOREIGN KEY (assigned_to) REFERENCES technicians(technician_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
    
);

CREATE TABLE IF NOT EXISTS cancellations (
    ticket_id INT PRIMARY KEY,
    -- cancellation_date DATE, -- Equals to created_at
    cancellation_reason TEXT,
    -- cancellation_responsible VARCHAR, -- The same creator

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ,
    updated_by VARCHAR,

    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id),
    FOREIGN KEY (cancellation_responsible) REFERENCES fsm_users(user_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS maintenances (
    maintenance_id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    ticket_id INT UNIQUE, -- Allow flexibility in the face of change: e.g ticket_id from INT a UUID to VARCHAR, different systems (clients) doing tk sends, it's necessary recreate or reimport tk

    maintenance_date DATE,
    maintenance_description TEXT,
    labsdl_id INT,
    -- carpeta_soporte TEXT,
    -- formato_soporte TEXT, -- worksheet 1:1 maintenance
    initial_photo_path TEXT, -- before 'archivo_foto_inicio'
    -- url_foto_inicio TEXT, -- the url is generated instantly by minio with presigned_get_object: Client sends request with JWT token -> Backend validates token (get_current_user) -> Backend fetches storage_path from DB -> Backend generates fresh presigned URL -> Returns URL to client -> Client downloads file directly from MinIO
    -- url_informe_soporte TEXT, -- worksheet 1:1 maintenance, and the url is generated instantly by minio with presigned_get_object
    -- maintenance_start TIMESTAMPTZ, -- equals to created_at
    real_mark_as VARCHAR,
    observations TEXT,
    edition_start TIMESTAMPTZ,
    
    -- nombre_recibe TEXT,
    -- cedula_recibe VARCHAR,
    -- cargo_recibe TEXT,
    -- sap_recibe VARCHAR,
    -- consecutivo_fus INT,
    -- firma_recibe TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ,
    updated_by VARCHAR,

    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id),
    FOREIGN KEY (labsdl_id) REFERENCES labsdls(labsdl_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS maintenances_technicians (
    -- id_mantenimiento_tecnico TEXT PRIMARY KEY, -- Necessary for appsheet, but here that is not the case 
    maintenance_id UUID,
    technician_id INT,
    start_hour TIMETZ,
    end_hour TIMETZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ,
    updated_by VARCHAR,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id),
    FOREIGN KEY (technician_id) REFERENCES technicians(technician_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS maintenances_spares (
    -- id_mantenimiento_repuesto TEXT PRIMARY KEY, -- Necessary for appsheet, but here that is not the case
    maintenance_id UUID,
    spare_id INT,
    qty NUMERIC(6,2),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ,
    updated_by VARCHAR,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id),
    FOREIGN KEY (spare_id) REFERENCES spares(spare_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS photos (
    photo_id TEXT PRIMARY KEY, 
    maintenance_id UUID,
    photo_path TEXT,
    -- url_foto TEXT, -- the url is generated instantly by minio with presigned_get_object
    processed BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ, -- photos rarely need to be edited. Consider delete this field
    updated_by VARCHAR,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS pauses (
    pause_id TEXT PRIMARY KEY, 
    maintenance_id UUID,
    -- pause_timestamp TIMESTAMPTZ, -- equals to created_at
    pause_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ,
    updated_by VARCHAR,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

-- =========================
-- ADTICKETS WEEKEND
-- =========================

CREATE TABLE IF NOT EXISTS adticketswkd (
    ticket_id INT PRIMARY KEY,

    operation_percentage NUMERIC,
    market_temperature NUMERIC,
    operation_damage BOOLEAN,
    completed BOOLEAN,
    observations_wkd TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR,
    updated_at TIMESTAMPTZ,
    updated_by VARCHAR,

    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id),
    FOREIGN KEY (created_by) REFERENCES fsm_users(user_id),
    FOREIGN KEY (updated_by) REFERENCES fsm_users(user_id)
);

-- =========================
-- EXTENSIONS (NOT AUDIT)
-- =========================

CREATE TABLE IF NOT EXISTS materials (
    material_id SERIAL PRIMARY KEY,
    ticket_id INT,
    maintenance_id UUID,
    spare_id INT, -- to be reset
    material_description TEXT,
    qty NUMERIC,
    price NUMERIC,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id),
    FOREIGN KEY (spare_id) REFERENCES spares(spare_id)
);

CREATE TABLE IF NOT EXISTS services (
    service_id SERIAL PRIMARY KEY,
    ticket_id INT,
    maintenance_id UUID,
    service_description TEXT,
    qty NUMERIC,
    price NUMERIC,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id)
);

-- =========================
-- OTHERS
-- =========================

CREATE TABLE IF NOT EXISTS hollidays ( -- Is it necessary? Hollidays is a 3rd part package in API
    holliday_date DATE PRIMARY KEY,
    title TEXT
);

CREATE TABLE IF NOT EXISTS preliquidated (
    ticket_id INT PRIMARY KEY,
    timestamp_write_form TIMESTAMPTZ,

    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
);

-- =========================
-- METADATA
-- =========================

CREATE TABLE IF NOT EXISTS uploads_sessions (
    upload_id        UUID        PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id          INT         NOT NULL,

    parent_tab       UUID        NOT NULL,
    parent_id        UUID        NOT NULL,
    tab_name         TEXT        NOT NULL,
    col_name         TEXT        NOT NULL,

    content_type     TEXT        NOT NULL,           
    total_size       INTEGER     NOT NULL,          
    total_chunks     INTEGER     NOT NULL,
    received_chunks  INTEGER     NOT NULL, 

    expires_at       TIMESTAMPTZ NOT NULL,
    completed        BOOLEAN,

    FOREIGN KEY (user_id) REFERENCES fsm_users(user_id)
);

CREATE TABLE IF NOT EXISTS worksheets(
    worksheet_id INTEGER PRIMARY KEY,
    maintenance_id UUID,
	
    receiver_name VARCHAR(150),
    receiver_doc_id VARCHAR(50),
    receiver_position VARCHAR(100),
    receiver_sap VARCHAR(50),
    receiver_signature TEXT,
    receiver_signature_timestamp TIMESTAMP WITH TIME ZONE,
	
    sheet_number VARCHAR(30) UNIQUE,
    pdf_url VARCHAR(100),
    generated_at TIMESTAMP WITH TIME ZONE,
    closed BOOLEAN,

    FOREIGN KEY (maintenance_id) REFERENCES maintenances(maintenance_id)
);