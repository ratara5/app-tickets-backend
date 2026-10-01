-- ============================================================================
-- GENERATED FILE - DO NOT EDIT BY HAND
-- ============================================================================
--
--   Artifact : infra/schema.sql
--   Kind     : schema-only, no data. This is a *derived* artifact.
--   Source   : live database "db_gestiket_acme" on the shared instance
--   Image    : infrastructure-companies-postgres-gci
--   Method   : pg_dump -U postgres --schema-only --no-owner --no-privileges
--   Repo sha : 88b02a8f16eaa5bbaa0b9efdf23a911b604fc63a
--   Dumped   : 2026-09-30
--   Contains : 23 tables, 2 enum types, 1 extension (pg_uuidv7)
--
-- WHY THIS FILE EXISTS
--
--   One dump, two outputs. This file is the dev/disposable bootstrap, and the
--   same dump is the source for the Alembic baseline revision. Both derive from
--   this single snapshot, so they cannot disagree with each other or with the
--   database that runs in production.
--
--   It replaces `init.sql`, which is retired. See TICKET-017.
--
-- DO NOT
--
--   * Edit. Any change must be made as a migration, then this file regenerated.
--   * Use it in production. Production runs `alembic upgrade head`.
--   * Use it to create the database itself. It creates tables inside a database
--     that must already exist. Creating the database is an admin action, run
--     once, deliberately separate from this file. See docs/deployment-guide.md 2.1.
--
-- REQUIRES
--
--   The custom image `infrastructure-companies-postgres-gci`. This schema uses
--   the third-party extension `pg_uuidv7` (see CREATE EXTENSION below). Stock
--   `postgres:16` does not ship it, so the load fails on a standard server.
--   See TICKET-007.
--
-- KNOWN GAPS IN THIS SNAPSHOT
--
--   * `hollidays`, `materials`, `preliquidated`, `services`, `uom` exist here but
--     have no ORM model. They back features that were never built. Decision
--     pending: TICKET-018. `uom` in particular cannot express a unit's
--     relationship to two different reference units, because `unit` is its
--     primary key.
--   * The schema and the ORM models agree. `alembic check` reports nothing
--     against the database this file was taken from, which took two revisions:
--     the models were reconciled in TICKET-019, then the database was brought up
--     to the models in TICKET-019's second half. Every table has a primary key.
--   * A restore of a backup taken from this schema reproduces every constraint,
--     including all 38 foreign keys. That was not true until TICKET-024: three
--     rows violated two of them, so `pg_dump` could not recreate those two and
--     `psql` still exited 0.
--
-- REGENERATE
--
--   Do NOT redirect the dump over this file. `>` truncates the hand-written
--   header above, which is the part that explains what the file is. The header
--   also changes length whenever its wording changes, so its size must be
--   derived rather than hardcoded -- a hardcoded line number silently truncates
--   the header as soon as the header grows.
--
--   # 1. Dump the body.
--   docker exec postgres-gci pg_dump -U postgres --schema-only \
--       --no-owner --no-privileges -d db_gestiket_acme > /tmp/schema-body.sql
--
--   # 2. Find the last rule of the header: everything before the pg_dump preamble.
--   BODY=$(grep -n '^-- PostgreSQL database dump' infra/schema.sql | head -1 | cut -d: -f1)
--   HDR=$(grep -n '^-- =\{20,\}$' infra/schema.sql | awk -F: -v b="$BODY" '$1<b {n=$1} END{print n}')
--
--   # 3. Rebuild: header, one blank line, then the new body.
--   { sed -n "1,${HDR}p" infra/schema.sql; echo; cat /tmp/schema-body.sql; } \
--       > /tmp/schema.sql
--   sed -i 's/^--   Repo sha : .*/--   Repo sha : <sha>/'  /tmp/schema.sql
--   sed -i 's/^--   Dumped   : .*/--   Dumped   : <YYYY-MM-DD>/' /tmp/schema.sql
--
--   # 4. Review every changed line before committing.
--   diff <(grep -v '^\\\(un\)\?restrict' infra/schema.sql) \
--        <(grep -v '^\\\(un\)\?restrict' /tmp/schema.sql)
--   mv /tmp/schema.sql infra/schema.sql
--
--   The body should change only where the migration changed something. `pg_dump`
--   emits a fresh random `\restrict` token on every run, which is why step 4
--   filters it out.
--
--   `tests/test_deploy_assets.py` asserts this header stays intact so the file
--   is never mistaken for a hand-maintained one.
-- ============================================================================

--
-- PostgreSQL database dump
--

\restrict Ggm737CnWDzVJlrTLLRzceeKZnYKnXJJyuVH8LO7PmXeVc7vdm4UMt7iPYj8RG1

-- Dumped from database version 16.13 (Debian 16.13-1.pgdg13+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_uuidv7; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_uuidv7 WITH SCHEMA public;


--
-- Name: EXTENSION pg_uuidv7; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_uuidv7 IS 'pg_uuidv7: create UUIDv7 values in postgres';


--
-- Name: priority_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.priority_type AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH'
);


--
-- Name: status_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.status_type AS ENUM (
    'OPEN',
    'ASSIGNED',
    'CANCELLED',
    'IN PROGRESS',
    'PAUSED',
    'CLOSED',
    'SIGNED'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: adticketswkd; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.adticketswkd (
    ticket_id integer NOT NULL,
    operation_percentage numeric,
    market_temperature numeric,
    operation_damage boolean,
    completed boolean,
    observations_wkd text,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(64) NOT NULL
);


--
-- Name: cancellations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cancellations (
    ticket_id integer NOT NULL,
    cancellation_reason text,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: equipments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.equipments (
    equipment_id integer NOT NULL,
    equipment_name character varying
);


--
-- Name: fsm_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fsm_users (
    user_id integer NOT NULL,
    email character varying(150) NOT NULL,
    user_name character varying(50) NOT NULL,
    passwd character varying(255) NOT NULL,
    user_role character varying(50) NOT NULL,
    photo_path character varying(500),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: fsm_users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.fsm_users_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: fsm_users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.fsm_users_user_id_seq OWNED BY public.fsm_users.user_id;


--
-- Name: hollidays; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hollidays (
    holliday_date date NOT NULL,
    title text
);


--
-- Name: labsdls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.labsdls (
    labsdl_id integer NOT NULL,
    labsdl_name character varying,
    labsdl_description character varying,
    hourly_rate numeric(8,2)
);


--
-- Name: labsdls_labsdl_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.labsdls_labsdl_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: labsdls_labsdl_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.labsdls_labsdl_id_seq OWNED BY public.labsdls.labsdl_id;


--
-- Name: maintenances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.maintenances (
    maintenance_id uuid DEFAULT public.uuid_generate_v7() NOT NULL,
    ticket_id integer,
    maintenance_date date,
    maintenance_description text,
    labsdl_id integer,
    initial_photo_path text,
    observations text,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: maintenances_spares; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.maintenances_spares (
    maintenance_id uuid NOT NULL,
    spare_id integer NOT NULL,
    qty numeric(6,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: maintenances_technicians; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.maintenances_technicians (
    maintenance_id uuid NOT NULL,
    technician_id integer NOT NULL,
    start_hour time without time zone NOT NULL,
    end_hour time without time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: markets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.markets (
    market_id integer NOT NULL,
    market_name character varying,
    city character varying,
    transport_cost numeric(8,2)
);


--
-- Name: materials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.materials (
    material_id integer NOT NULL,
    ticket_id integer,
    maintenance_id uuid,
    spare_id integer,
    material_description text,
    qty numeric,
    price numeric
);


--
-- Name: materials_material_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.materials_material_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: materials_material_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.materials_material_id_seq OWNED BY public.materials.material_id;


--
-- Name: pauses_pause_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pauses_pause_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pauses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pauses (
    pause_id integer DEFAULT nextval('public.pauses_pause_id_seq'::regclass) NOT NULL,
    maintenance_id uuid NOT NULL,
    pause_reason text,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.photos (
    photo_id text NOT NULL,
    maintenance_id uuid,
    photo_path text,
    processed boolean,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: preliquidated; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preliquidated (
    ticket_id integer NOT NULL,
    timestamp_write_form timestamp with time zone
);


--
-- Name: services; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.services (
    service_id integer NOT NULL,
    ticket_id integer,
    maintenance_id uuid,
    service_description text,
    qty numeric,
    price numeric
);


--
-- Name: services_service_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.services_service_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: services_service_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.services_service_id_seq OWNED BY public.services.service_id;


--
-- Name: spares; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spares (
    spare_id integer NOT NULL,
    spare_name character varying,
    unit character varying,
    price numeric(10,2)
);


--
-- Name: spares_spare_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.spares_spare_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: spares_spare_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.spares_spare_id_seq OWNED BY public.spares.spare_id;


--
-- Name: technicians; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.technicians (
    technician_id integer NOT NULL,
    user_id integer NOT NULL
);


--
-- Name: tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tickets (
    ticket_id integer NOT NULL,
    priority public.priority_type,
    market_id integer,
    ticket_date date,
    equipment_id integer,
    ticket_description character varying,
    status public.status_type,
    assigned_to integer,
    created_at timestamp with time zone DEFAULT now(),
    created_by integer,
    updated_at timestamp with time zone,
    updated_by integer
);


--
-- Name: token_blacklist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.token_blacklist (
    jti uuid NOT NULL,
    expires_at timestamp without time zone NOT NULL
);


--
-- Name: uom; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.uom (
    unit character varying NOT NULL,
    magnitude character varying,
    uom_description text,
    ref_unit character varying,
    factor_conversion numeric(20,10)
);


--
-- Name: uploads_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.uploads_sessions (
    upload_id uuid DEFAULT public.uuid_generate_v7() NOT NULL,
    user_id integer NOT NULL,
    parent_tab text NOT NULL,
    parent_id uuid NOT NULL,
    tab_name text NOT NULL,
    col_name text NOT NULL,
    content_type text NOT NULL,
    total_size integer NOT NULL,
    total_chunks integer NOT NULL,
    received_chunks integer NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    completed boolean,
    replaces_photo_id integer
);


--
-- Name: worksheets_worksheet_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.worksheets_worksheet_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: worksheets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.worksheets (
    worksheet_id integer DEFAULT nextval('public.worksheets_worksheet_id_seq'::regclass) NOT NULL,
    maintenance_id uuid NOT NULL,
    receiver_name character varying(150),
    receiver_doc_id character varying(50),
    receiver_position character varying(100),
    receiver_sap character varying(50),
    receiver_signature text,
    receiver_signature_timestamp timestamp with time zone,
    sheet_number character varying(30),
    pdf_path character varying(100),
    generated_at timestamp with time zone,
    closed boolean
);


--
-- Name: fsm_users user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fsm_users ALTER COLUMN user_id SET DEFAULT nextval('public.fsm_users_user_id_seq'::regclass);


--
-- Name: labsdls labsdl_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labsdls ALTER COLUMN labsdl_id SET DEFAULT nextval('public.labsdls_labsdl_id_seq'::regclass);


--
-- Name: materials material_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials ALTER COLUMN material_id SET DEFAULT nextval('public.materials_material_id_seq'::regclass);


--
-- Name: services service_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services ALTER COLUMN service_id SET DEFAULT nextval('public.services_service_id_seq'::regclass);


--
-- Name: spares spare_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spares ALTER COLUMN spare_id SET DEFAULT nextval('public.spares_spare_id_seq'::regclass);


--
-- Name: adticketswkd adticketswkd_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adticketswkd
    ADD CONSTRAINT adticketswkd_pkey PRIMARY KEY (ticket_id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: cancellations cancellations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancellations
    ADD CONSTRAINT cancellations_pkey PRIMARY KEY (ticket_id);


--
-- Name: equipments equipments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.equipments
    ADD CONSTRAINT equipments_pkey PRIMARY KEY (equipment_id);


--
-- Name: fsm_users fsm_users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fsm_users
    ADD CONSTRAINT fsm_users_email_key UNIQUE (email);


--
-- Name: fsm_users fsm_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fsm_users
    ADD CONSTRAINT fsm_users_pkey PRIMARY KEY (user_id);


--
-- Name: hollidays hollidays_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hollidays
    ADD CONSTRAINT hollidays_pkey PRIMARY KEY (holliday_date);


--
-- Name: labsdls labsdls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.labsdls
    ADD CONSTRAINT labsdls_pkey PRIMARY KEY (labsdl_id);


--
-- Name: maintenances maintenances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances
    ADD CONSTRAINT maintenances_pkey PRIMARY KEY (maintenance_id);


--
-- Name: maintenances_spares maintenances_spares_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_spares
    ADD CONSTRAINT maintenances_spares_pkey PRIMARY KEY (maintenance_id, spare_id);


--
-- Name: maintenances_technicians maintenances_technicians_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_technicians
    ADD CONSTRAINT maintenances_technicians_pkey PRIMARY KEY (maintenance_id, technician_id);


--
-- Name: markets markets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.markets
    ADD CONSTRAINT markets_pkey PRIMARY KEY (market_id);


--
-- Name: materials materials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_pkey PRIMARY KEY (material_id);


--
-- Name: pauses pauses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pauses
    ADD CONSTRAINT pauses_pkey PRIMARY KEY (pause_id);


--
-- Name: photos photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_pkey PRIMARY KEY (photo_id);


--
-- Name: preliquidated preliquidated_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preliquidated
    ADD CONSTRAINT preliquidated_pkey PRIMARY KEY (ticket_id);


--
-- Name: services services_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_pkey PRIMARY KEY (service_id);


--
-- Name: spares spares_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spares
    ADD CONSTRAINT spares_pkey PRIMARY KEY (spare_id);


--
-- Name: technicians technicians_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.technicians
    ADD CONSTRAINT technicians_pkey PRIMARY KEY (technician_id);


--
-- Name: technicians technicians_user_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.technicians
    ADD CONSTRAINT technicians_user_id_unique UNIQUE (user_id);


--
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (ticket_id);


--
-- Name: token_blacklist token_blacklist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.token_blacklist
    ADD CONSTRAINT token_blacklist_pkey PRIMARY KEY (jti);


--
-- Name: uom uom_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uom
    ADD CONSTRAINT uom_pkey PRIMARY KEY (unit);


--
-- Name: uploads_sessions uploads_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uploads_sessions
    ADD CONSTRAINT uploads_sessions_pkey PRIMARY KEY (upload_id);


--
-- Name: maintenances uq_maintenances_ticket_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances
    ADD CONSTRAINT uq_maintenances_ticket_id UNIQUE (ticket_id);


--
-- Name: worksheets worksheets_maintenance_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worksheets
    ADD CONSTRAINT worksheets_maintenance_id_key UNIQUE (maintenance_id);


--
-- Name: worksheets worksheets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worksheets
    ADD CONSTRAINT worksheets_pkey PRIMARY KEY (worksheet_id);


--
-- Name: worksheets worksheets_sheet_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worksheets
    ADD CONSTRAINT worksheets_sheet_number_key UNIQUE (sheet_number);


--
-- Name: fki_technicians_user_id_fkey; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fki_technicians_user_id_fkey ON public.technicians USING btree (user_id);


--
-- Name: adticketswkd adticketswkd_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adticketswkd
    ADD CONSTRAINT adticketswkd_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: adticketswkd adticketswkd_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adticketswkd
    ADD CONSTRAINT adticketswkd_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: adticketswkd adticketswkd_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adticketswkd
    ADD CONSTRAINT adticketswkd_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: cancellations cancellations_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancellations
    ADD CONSTRAINT cancellations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: cancellations cancellations_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancellations
    ADD CONSTRAINT cancellations_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: cancellations cancellations_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cancellations
    ADD CONSTRAINT cancellations_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: maintenances maintenances_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances
    ADD CONSTRAINT maintenances_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: maintenances maintenances_labsdl_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances
    ADD CONSTRAINT maintenances_labsdl_id_fkey FOREIGN KEY (labsdl_id) REFERENCES public.labsdls(labsdl_id);


--
-- Name: maintenances_spares maintenances_spares_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_spares
    ADD CONSTRAINT maintenances_spares_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: maintenances_spares maintenances_spares_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_spares
    ADD CONSTRAINT maintenances_spares_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- Name: maintenances_spares maintenances_spares_spare_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_spares
    ADD CONSTRAINT maintenances_spares_spare_id_fkey FOREIGN KEY (spare_id) REFERENCES public.spares(spare_id);


--
-- Name: maintenances_spares maintenances_spares_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_spares
    ADD CONSTRAINT maintenances_spares_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: maintenances_technicians maintenances_technicians_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_technicians
    ADD CONSTRAINT maintenances_technicians_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: maintenances_technicians maintenances_technicians_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_technicians
    ADD CONSTRAINT maintenances_technicians_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- Name: maintenances_technicians maintenances_technicians_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_technicians
    ADD CONSTRAINT maintenances_technicians_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.technicians(technician_id);


--
-- Name: maintenances_technicians maintenances_technicians_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances_technicians
    ADD CONSTRAINT maintenances_technicians_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: maintenances maintenances_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances
    ADD CONSTRAINT maintenances_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: maintenances maintenances_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.maintenances
    ADD CONSTRAINT maintenances_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: materials materials_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- Name: materials materials_spare_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_spare_id_fkey FOREIGN KEY (spare_id) REFERENCES public.spares(spare_id);


--
-- Name: pauses pauses_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pauses
    ADD CONSTRAINT pauses_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: pauses pauses_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pauses
    ADD CONSTRAINT pauses_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- Name: pauses pauses_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pauses
    ADD CONSTRAINT pauses_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: photos photos_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: photos photos_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- Name: photos photos_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: preliquidated preliquidated_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preliquidated
    ADD CONSTRAINT preliquidated_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(ticket_id);


--
-- Name: services services_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- Name: spares spares_unit_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spares
    ADD CONSTRAINT spares_unit_fkey FOREIGN KEY (unit) REFERENCES public.uom(unit);


--
-- Name: technicians technicians_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.technicians
    ADD CONSTRAINT technicians_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.fsm_users(user_id);


--
-- Name: tickets tickets_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.technicians(technician_id);


--
-- Name: tickets tickets_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.fsm_users(user_id);


--
-- Name: tickets tickets_equipment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_equipment_id_fkey FOREIGN KEY (equipment_id) REFERENCES public.equipments(equipment_id);


--
-- Name: tickets tickets_market_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_market_id_fkey FOREIGN KEY (market_id) REFERENCES public.markets(market_id);


--
-- Name: tickets tickets_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.fsm_users(user_id);


--
-- Name: uom uom_ref_unit_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uom
    ADD CONSTRAINT uom_ref_unit_fkey FOREIGN KEY (ref_unit) REFERENCES public.uom(unit);


--
-- Name: uploads_sessions uploads_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.uploads_sessions
    ADD CONSTRAINT uploads_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.fsm_users(user_id);


--
-- Name: worksheets worksheets_maintenance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worksheets
    ADD CONSTRAINT worksheets_maintenance_id_fkey FOREIGN KEY (maintenance_id) REFERENCES public.maintenances(maintenance_id);


--
-- PostgreSQL database dump complete
--

\unrestrict Ggm737CnWDzVJlrTLLRzceeKZnYKnXJJyuVH8LO7PmXeVc7vdm4UMt7iPYj8RG1

