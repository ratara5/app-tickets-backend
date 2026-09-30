# Bug: init.sql declares a VARCHAR foreign key onto a SERIAL primary key, so 13 tables are never created

## Metadata

- **Summary**: PostgreSQL refuses the FK at init.sql:115, and every table declared after it is skipped
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment

## Description

`init.sql` types `fsm_users.user_id` as `SERIAL` (integer) but declares:

```sql
created_by VARCHAR,
FOREIGN KEY (created_by) REFERENCES fsm_users(user_id)
```

PostgreSQL cannot implement a foreign key between `character varying` and `integer`, and it
rejects the statement. The tables created after that line (tickets, maintenances, photos,
uploads_sessions, worksheets and their join tables) are therefore never created, even on a
server that has `pg_uuidv7` installed.

**Impact:** `init.sql` cannot build a complete schema on any server, so it is not a usable
installation path. Combined with TICKET-007 the failure is silent.

## Reproduction

```bash
docker run -d --name probe -e POSTGRES_PASSWORD=x postgres:16
docker exec probe psql -U postgres -c "CREATE DATABASE d"
docker exec -i probe psql -v ON_ERROR_STOP=1 -U postgres -d d < init.sql
```

Observed: `ERROR: foreign key constraint "tickets_created_by_fkey" cannot be implemented /
DETAIL: Key columns "created_by" and "user_id" are of incompatible types: character varying
and integer.` The load stops with 7 tables created and 14 missing.

## Notes

- The models use `Integer` for `user_id` (`app/models/fsm_user.py:10`), so the correct fix is a
  type decision, not a cast in the FK clause.
- The deviation between `init.sql` and the models is the underlying problem: `init.sql` is a
  legacy artifact that no longer matches the schema Alembic and SQLAlchemy consider
  authoritative. Consider whether it should be regenerated from the models or retired.

## Resolution

Resolved by TICKET-017. `init.sql` is gone, so the unbuildable statement is gone
with it. In the schema of record that replaces it, `created_by` is `integer` on
every table that has one, matching `fsm_users.user_id`, so the foreign key is
implementable.

Verified by reading the current dump rather than by trusting the ticket's account
of it: the type is consistent across all tables, not only the one named.
