-- ============================================================================
-- 001-create-application-roles.sql
-- ============================================================================
-- Creates the single least-privilege role this application needs, and takes
-- away everything it does not need.
--
-- ONE ROLE, NOT TWO. An earlier version of this file created a second
-- "migration" role holding CREATE on the schema, on the theory that DDL should
-- be separated from DML. That was wrong, and not for a policy reason but a
-- mechanical one: GRANT CREATE ON SCHEMA permits creating NEW objects, not
-- altering existing ones. In PostgreSQL, ALTER and DROP require ownership, and
-- ownership was deliberately never granted to any application role. The
-- migration role could therefore create an empty table and could not alter a
-- single real one — it could not do the job it existed for, and the test that
-- appeared to prove otherwise had only exercised a table it had just created.
--
-- Rather than transfer ownership to a migration role — which would put every
-- table under a credential that exists to change the schema — the split is
-- removed. Schema change belongs to the administrator who owns the schema, and
-- the running service has no part in it. This is also the convention the
-- sibling project converged on, and it is the simpler one:
--
--   <runtime>_app   DML on this database's tables. Cannot ALTER, DROP, or
--                   CREATE. Owns nothing. Holds no capability attribute.
--
--   migrations      run by an administrator, as the schema's owner. Not a
--                   provisioned role, not a credential, not a job.
--
-- ── Before running ────────────────────────────────────────────────────────
-- 1. Replace every <placeholder> below. Do not leave a literal in place.
-- 2. Confirm the names are free, or you will collide with another app:
--        docker exec -it <pg-container> psql -U <admin-user> -c '\du'
--        docker exec -it <pg-container> psql -U <admin-user> -c '\l'
-- 3. Generate a real password. Do not put it in this file, in a compose file,
--    or in the repository. `openssl rand -base64 32` is adequate.
--
-- ── Deliberately NOT included ─────────────────────────────────────────────
-- No CREATE DATABASE. The database is created empty, by an administrator, and
-- then populated from the schema of record. The application never holds
-- CREATEDB, so it can never create a second schema to drift from.
--
-- No ALTER ... OWNER TO. Ownership is never transferred. A grantee is not an
-- owner: an owner can drop its own objects and reshape the schema, a grantee
-- cannot. That asymmetry is the entire point of this file.
--
-- No REVOKE on databases belonging to other applications. See step 3.
--
-- The role name below is a placeholder. This file is deliberately not
-- parameterised: it is short, reviewable, and run by a person who can read it.
-- =============================================================================


-- ── 1. The runtime role ────────────────────────────────────────────────────
-- NOLOGIN is not used: the service must connect. Every capability attribute is
-- named explicitly as NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION rather
-- than left to the server defaults, so that a hardened `postgresql.conf` cannot
-- change what this role is.
CREATE ROLE <runtime>_app WITH LOGIN
  PASSWORD '<generated-password>'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOINHERIT;


-- ── 2. Reachability of THIS role on THIS instance ─────────────────────────
-- Object-level privileges are the second line of defence, not the first. The
-- first is the network boundary in step 3. Both are needed: a GRANT controls
-- what a role may do once connected, and nothing controls which database it is
-- allowed to reach in the first place.
--
-- Revoke the default PUBLIC privilege on the target database, so that no other
-- role on the shared instance can connect to it, then grant CONNECT back to the
-- one role that should be there. This statement must run while connected to
-- `postgres`, not to the target database.
REVOKE ALL ON DATABASE <database> FROM PUBLIC;
GRANT CONNECT ON DATABASE <database> TO <runtime>_app;


-- ── 3. Do NOT revoke CONNECT from other applications' databases ───────────
-- Every role on a PostgreSQL server inherits CONNECT on every database from the
-- PUBLIC pseudo-role. Revoking that from PUBLIC is the obvious-looking fix for
-- "our app can reach their data", and it is the wrong one here, for two reasons.
--
-- First, it does not do what the instinct expects. REVOKE is per database. It
-- does not make the server-wide, it makes that one database unreachable to
-- everyone who was relying on the default, and every other sibling database
-- keeps its PUBLIC CONNECT exactly as before. An application that believes it
-- has isolated itself has not.
--
-- Second, it is someone else's change to make. Revoking from PUBLIC on a
-- database this project does not own breaks whichever tenant depends on the
-- default, from code that has never heard of this file. Doing that as a routine
-- step of onboarding one application is how a shared instance gets taken down.
--
-- Isolation that is actually enforced, and is scoped to one role, is the
-- host-based rule in step 4. It is enforced by the server before any SQL runs,
-- it needs no privileges revoked from anyone, and it cannot affect a tenant this
-- project has nothing to do with. The sibling project documents the same
-- requirement; that warning is the reason this file does not attempt to
-- substitute a GRANT for it.
--
-- To see what a role can currently reach, inventory the instance:
--
--   SELECT datname, datacl FROM pg_database ORDER BY datname;
--
-- A NULL datacl means "default": that database's CONNECT still comes from
-- PUBLIC. Read-only; this file changes nothing here.


-- ── 4. Enforce reachability at the network layer ───────────────────────────
-- pg_hba.conf is evaluated in order and the first match wins, so the deny-all
-- line MUST come after the allow line, and both must be above any broader rule
-- already in the file. This cannot be done from SQL: it is cluster
-- configuration, it applies to every database at once, and it is scoped to one
-- role.
--
-- Insert into the container's pg_hba.conf, ABOVE any broader rule already
-- present, then reload (not restart) the server:
--
-- DO NOT APPEND. Placement is the whole rule. `pg_hba.conf` is first-match, and
-- a shared instance ends with catch-alls such as
--
--     host    all    all    0.0.0.0/0    scram-sha-256
--     host    all    all    ::/0         scram-sha-256
--
-- which match before anything appended beneath them. A rule at the bottom of the
-- file is DEAD: the role stays reachable from every address while this file
-- claims to have stopped it, and nothing in the running service can tell you.
-- Check where you are inserting, and put the two lines above the first broader
-- line. Corrected 2026-09-30; the instruction here previously said "Append",
-- two lines below prose that said the opposite. The prose was right.
--
--   # TYPE     DATABASE     USER               ADDRESS        METHOD
--   host      <database>   <runtime>_app      <app-cidr>     scram-sha-256
--   host      all          <runtime>_app      0.0.0.0/0      reject
--
-- <app-cidr> is deliberately left as a placeholder and cannot be resolved by
-- whoever writes this file. The address in the allow line is the one the SERVER
-- sees, which is not always the one the client used: Docker re-originates a
-- host-initiated connection to the bridge gateway, so on the measured instance
-- `127.0.0.1:5435` arrives as `172.19.0.1/32`. An allow line written for
-- `127.0.0.1/32` therefore never matches, and the symptom is a rejection with a
-- correct role and a correct password. Read the real subnet from the deployment
-- network after it is created. Do not hardcode a plausible-looking guess either:
-- on a host with many bridges most subnets are already allocated to a tenant,
-- and an overlapping one produces routing that depends on start order.
--
-- Check first, and reload rather than restart so in-flight connections survive:
--
--   docker exec -it <pg-container> psql -U <admin-user> -c 'SHOW hba_file;'
--   docker exec -it <pg-container> psql -U <admin-user> -c 'SELECT pg_reload_conf();'
--
-- After reloading, verify the deny line actually bites — connect to a database
-- this application does not own and confirm it is rejected. Until that is
-- observed, the isolation this file is credited with does not exist yet.


-- ── 5. Schema-level privileges inside the target database ─────────────────
-- Everything below runs against the TARGET database, not postgres.
\connect <database>

-- PostgreSQL 15 and later no longer grant CREATE on the public schema to
-- PUBLIC, but an existing database may still carry the older grant. Revoke it
-- explicitly so the result does not depend on the server's major version.
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- USAGE lets the role resolve object names. It does NOT grant CREATE, so the
-- role can read the schema's structure and cannot add to it. That is the whole
-- difference between a DML role and a DDL one.
GRANT USAGE ON SCHEMA public TO <runtime>_app;


-- ── 6. Table and sequence privileges ──────────────────────────────────────
-- Take away the ability to discover objects the role has not been granted.
-- Without this, a role can read every table and column name in the schema even
-- in tables it cannot SELECT from.
--
-- The object owner for these default privileges MUST be the role that will
-- create the objects — the administrator who loads the schema, not
-- <runtime>_app. ALTER DEFAULT PRIVILEGES is a statement about future objects
-- created BY a named role; naming the wrong role here produces a script that
-- looks correct and grants nothing to anything.
ALTER DEFAULT PRIVILEGES FOR ROLE <admin> IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO <runtime>_app;
ALTER DEFAULT PRIVILEGES FOR ROLE <admin> IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO <runtime>_app;

-- Existing objects are not covered by ALTER DEFAULT PRIVILEGES, so the grants
-- have to be applied to what is already there. This is why the roles are
-- provisioned AFTER the schema of record is loaded.
--
-- The table list is NAMED, not `ON ALL TABLES`, and that is the whole point of
-- this section. The database holds 23 tables and the application models 17.
-- The other six are `alembic_version` (Alembic's own bookkeeping, needed only
-- by whoever runs a migration) and the five tables reserved for features that
-- were never built — hollidays, materials, preliquidated, services, uom
-- (TICKET-018). The application reads and writes none of them, and a service
-- credential that can INSERT, UPDATE or DELETE them is a credential that can
-- corrupt them after a compromise.
--
-- `ON ALL TABLES` was measurably looser: it handed the running service full
-- write access to all six. It was replaced on 2026-09-30 after reading the
-- code — `get_holidays` resolves dates from the `holidays` *Python package*,
-- not the `hollidays` table, and no module under app/ names uom, materials,
-- preliquidated or services at all.
--
-- Withholding SELECT on `uom` does NOT weaken `spares.unit` referential
-- integrity, which was the obvious risk and the reason to check rather than
-- assume. PostgreSQL's referential-integrity triggers run as the constraint
-- owner, not as the inserting role, so the application role needs no privilege
-- on the referenced table. Verified on a scratch database built from
-- infra/schema.sql with exactly these grants: INSERT into spares with a valid
-- unit succeeds, and INSERT with a non-existent unit still fails with
-- `violates foreign key constraint "spares_unit_fkey"`.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    adticketswkd,
    cancellations,
    equipments,
    fsm_users,
    labsdls,
    maintenances,
    maintenances_spares,
    maintenances_technicians,
    markets,
    pauses,
    photos,
    spares,
    technicians,
    tickets,
    token_blacklist,
    uploads_sessions,
    worksheets
TO <runtime>_app;

-- Sequences are named for the same reason. Two sequences in the live database
-- belong to reserved tables (materials_material_id_seq,
-- services_service_id_seq) and `ON ALL SEQUENCES` would have let the service
-- advance them. Without USAGE on the three that matter, every serial insert
-- fails at runtime — verified, not assumed: this is what a role with table DML
-- and no sequence grant does.
GRANT USAGE, SELECT ON SEQUENCE
    fsm_users_user_id_seq,
    labsdls_labsdl_id_seq,
    spares_spare_id_seq
TO <runtime>_app;

-- TRUNCATE, REFERENCES and TRIGGER are each a way to damage data or schema
-- while holding only table-level grants, and are deliberately absent.


-- ── 7. Verify, do not assume ──────────────────────────────────────────────
-- These are checks rather than steps, so they are commented out. Run them in a
-- separate psql session AS <runtime>_app for the privilege tests.
--
--   -- No capability attribute. Must return zero rows.
--   SELECT rolname FROM pg_roles
--    WHERE rolname = '<runtime>_app'
--      AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication);
--
--   -- Owns nothing. Must return zero rows. Ownership lives in the pg_ catalog,
--   -- NOT in information_schema.tables, which has no tableowner column; a query
--   -- written against it errors out and the check is quietly never done.
--   SELECT tablename FROM pg_tables
--    WHERE schemaname = 'public' AND tableowner = '<runtime>_app';
--
--   -- The next four must each fail with permission denied.
--   CREATE TABLE public.should_fail (id int);
--   DROP TABLE IF EXISTS public.<any-existing-table>;
--   ALTER TABLE public.<any-existing-table> ADD COLUMN should_fail int;
--   CREATE INDEX should_fail ON public.<any-existing-table> (unit);
--
--   -- These must all fail too. The role was never granted them, and a service
--   -- credential that can write the reserved tables can corrupt the data that
--   -- a future feature will be built on.
--   SELECT * FROM public.uom;              -- referenced by spares.unit, no SELECT needed
--   SELECT * FROM public.hollidays;         -- the app uses the `holidays` package, not this
--   SELECT * FROM public.materials;
--   SELECT * FROM public.preliquidated;
--   SELECT * FROM public.services;
--   SELECT * FROM public.alembic_version;   -- Alembic's bookkeeping, not the app's
--   SELECT nextval('materials_material_id_seq');
--
--   -- The next two must succeed.
--   SELECT count(*) FROM public.<any-existing-table>;
--   INSERT INTO public.<any-existing-table> (...) VALUES (...);   -- then roll back
--
--   -- Reachability. Must fail with a connection rejection, not a permission
--   -- error: step 4 is what makes this fail, and a permission error means
--   -- step 4 is not in effect.
--   psql -U <runtime>_app -d <some-other-application's-database> -c 'SELECT 1;'
--
-- The first two must be empty, the four DDL checks must fail, the two DML
-- checks must succeed, and the cross-database connection must be rejected. A
-- check that succeeds where it was expected to fail means the role has more
-- privilege than intended: fix it here, before the application is pointed at
-- it.
