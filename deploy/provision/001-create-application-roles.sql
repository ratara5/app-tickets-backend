-- ============================================================================
-- 001-create-application-roles.sql
-- ============================================================================
-- Creates the two least-privilege roles this application needs, separately.
--
-- WHY TWO ROLES: the runtime service does DML. Schema changes are a separate,
-- rarer, human-initiated act. Collapsing them into one role means a bug in the
-- service, or a compromised service credential, can drop a column. The sibling
-- project converged on a single owner role with GRANT ALL; that is simpler and
-- is a reasonable choice, but it cannot answer "what damage can the running
-- service do?" The split costs one extra variable and answers it.
--
--   <runtime>_app   DML on this database's tables. Cannot ALTER, DROP, or read
--                   the other applications' databases on the same server.
--   <runtime>_migr  DDL on this database's schema. Holds the password only when
--                   a migration is actually being run.
--
-- TWO-PLANE RULE: this is a Plane 1 (admin/one-time) operation. It is run by
-- hand with an administrator's psql session, never by `docker compose up`, never
-- from the app container, and never by a seed or migration job. A shared
-- instance's databases and credentials must not be created by an app's compose
-- file.
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
-- CREATEDB.
--
-- The role names below are placeholders. This file is deliberately not
-- parameterised: it is short, reviewable, and run by a person who can read it.
-- =============================================================================


-- ── 1. The runtime role ───────────────────────────────────────────────────
-- NOLOGIN is not used: the service must connect.
CREATE ROLE <runtime>_app WITH LOGIN PASSWORD '<generated-password>';

-- ── 2. The migration role ─────────────────────────────────────────────────
-- Holds schema-modification rights. In a production environment the password
-- is set once, used to run the migration, and then rotated.
CREATE ROLE <runtime>_migr WITH LOGIN PASSWORD '<generated-password>';


-- ── 3. Lock down what these roles may reach on the shared server ───────────
-- Every role on a PostgreSQL server inherits CONNECT on every database from the
-- PUBLIC pseudo-role, unless it is revoked. This was verified on a disposable
-- instance: a role that had been granted nothing whatsoever on a sibling
-- application's database could still connect to it, because PUBLIC held
-- CONNECT.
--
-- Isolation therefore depends on the SERVER-wide default, not on this
-- database's grants. The statement below is the one that actually closes it, and
-- it is what stops this application from reaching another application's data
-- later. It is listed here because the rest of the file is meaningless without
-- it, but see the warning: it is a server-wide change.
REVOKE CONNECT ON DATABASE postgres     FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1    FROM PUBLIC;

-- WARNING: REVOKE ... FROM PUBLIC is SERVER-WIDE and affects every application
-- on this shared instance, including ones this project has nothing to do with.
-- It will break any of them that relies on the default CONNECT without holding
-- an explicit grant.
--
-- Before running it, inventory the instance:
--
--   SELECT datname, datacl FROM pg_database ORDER BY datname;
--
-- A NULL datacl means "default", i.e. that database's CONNECT is still coming
-- from PUBLIC. For each such database belonging to another application, either
-- have its owner add an explicit grant, or accept that it loses access and tell
-- them first.
--
-- This statement is idempotent, and is often better applied once by whoever
-- administers the instance, rather than by each application separately. It is
-- kept in this file so the requirement is visible from the same place as the
-- grants it interacts with.

-- ── 4. Revoke the default PUBLIC privilege on the target database ─────────
-- PostgreSQL 15 and later no longer grant CREATE on the public schema to
-- PUBLIC, but an existing database may still carry the older grant. The next
-- statement is the fix for that, and it must run while connected to the target
-- database, not to postgres.
REVOKE ALL ON DATABASE <database> FROM PUBLIC;

-- Grant CONNECT explicitly to both roles. Nothing else on the database level.
GRANT CONNECT ON DATABASE <database> TO <runtime>_app, <runtime>_migr;


-- ── 5. Schema-level privileges inside the target database ────────────────
-- Everything below runs against the TARGET database, not postgres.
\connect <database>

-- No role other than the migration role may create objects in the schema. This
-- is the specific grant that PostgreSQL 15 removed from PUBLIC but that older
-- databases still carry.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO <runtime>_app;
GRANT USAGE, CREATE ON SCHEMA public TO <runtime>_migr;

-- Take away the ability to see objects the role has not been granted. Without
-- this, a role can discover table and column names in schemas it cannot read.
ALTER DEFAULT PRIVILEGES FOR ROLE <runtime>_migr IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO <runtime>_app;
ALTER DEFAULT PRIVILEGES FOR ROLE <runtime>_migr IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO <runtime>_app;

-- Existing objects are not covered by ALTER DEFAULT PRIVILEGES, so the grants
-- have to be applied to what is already there.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO <runtime>_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO <runtime>_app;


-- ── 6. Make the runtime role the owner of nothing ─────────────────────────
-- The application role is a grant recipient, never an owner. An owner can drop
-- its own objects and alter the schema; a grantee cannot. Ownership stays with
-- the role that built the schema.
--
-- VERIFY, do not assume. These are queries to run afterwards, so they are
-- commented out here and must be run in a separate psql session.
--
--   -- Neither role is privileged. Must return zero rows.
--   SELECT rolname FROM pg_roles
--    WHERE rolname IN ('<runtime>_app', '<runtime>_migr')
--      AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication);
--
--   -- The runtime role owns nothing. Must return zero rows.
--   SELECT table_name FROM information_schema.tables
--    WHERE table_schema='public' AND tableowner = '<runtime>_app';
--
--   -- The runtime role cannot create objects in the schema. Must error.
--   CREATE TABLE public.should_fail (id int);
--
--   -- The runtime role cannot reach another application's database. Requires
--   -- step 3 to have been applied server-wide; run it as <runtime>_app against
--   -- that database and it must fail with permission denied.
--
-- The first two must be empty, and the checks that issue DDL must fail. If a
-- check succeeds when it was expected to fail, the role has more privilege than
-- intended: fix it here, before the application is pointed at it.
