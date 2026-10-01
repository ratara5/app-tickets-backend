# Provisioning a database and roles on a shared PostgreSQL instance

These files are **Plane 1 (admin, one-time) operations**. They are run by hand
in an administrator's `psql` session. They are never executed by
`docker compose up`, by the application container, by a migration job, or by the
data loader.

A shared instance's databases and credentials must not be created by an
arbitrary application's compose file. The application does not hold the
credentials to create a database, and it should not.

## The order that matters

Database creation, schema load, role grants, and the network rule are four
separate acts, in this order:

1. **Create the database, empty**, as an administrator. Not owned by the
   application role. No schema yet.
2. **Load the schema of record** — `infra/schema.sql`, a dump of the live
   database. This creates every table, constraint, index, and extension.
3. **Create the roles and grant privileges** — `001-create-application-roles.sql`.
4. **Add the `pg_hba.conf` rule** for the role, and reload.

Grants come *after* the schema because the grants at the end of the SQL file
apply to existing objects, and `ALTER DEFAULT PRIVILEGES` only covers objects
created after it runs. Doing it the other way round leaves every current table
ungranted.

The `pg_hba.conf` rule comes last because it can be verified independently, and
because a role with no privileges is harmless until it is reachable.

## One role, not two

| Role            | Holds                                | Used for            |
|-----------------|--------------------------------------|---------------------|
| `<runtime>_app` | DML on the 17 modelled tables (below) | the running service |
| — *(administrator)* | ownership of the schema        | migrations         |

There is no migration role. That is a correction, not an omission, and it is
worth understanding before changing it back.

An earlier version of this file created a second role holding `CREATE` on the
schema, so that DDL would be separated from DML. The intent was to answer "what
damage can the running service do?" — but the mechanism did not do what it
looked like it did. In PostgreSQL, `GRANT CREATE ON SCHEMA` permits creating
*new* objects; `ALTER` and `DROP` on existing ones require **ownership**, and
ownership is never granted to an application role here. So the migration role
could create an empty table and could not alter a real one. It could not do the
job it existed for, and the test that appeared to prove otherwise had only
exercised a table that role had just created itself.

The two ways to make a real DDL role work are both worse than not having one:

- **Transfer ownership of every table to the migration role.** Now the
  credential that exists to reshape the schema owns the data, and the
  "ownership is never transferred" rule — the load-bearing part of this file —
  is gone.
- **Grant the migration role to the runtime role.** Then a compromised service
  credential has every capability the migration role has, which is the thing the
  split was supposed to prevent.

So schema change stays with the administrator who owns the schema, and the
running service has no part in it. Migrations are run by a human, as the owner,
the same way the schema of record is loaded in the first place. This also matches
what the sibling project converged on, and it is the simpler design.

Neither capability attribute is granted: the role is `NOSUPERUSER`,
`NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, and `NOINHERIT`, all named
explicitly rather than inherited from server defaults. The application role owns
nothing — it is a grant recipient, never an owner.

## Why the table list is named, not `ON ALL TABLES`

The database holds 23 tables. The application models 17. The remaining six are
`alembic_version` — Alembic's own bookkeeping, needed only by whoever runs a
migration — and the five tables reserved for features that were never built:
`hollidays`, `materials`, `preliquidated`, `services`, `uom` (TICKET-018).

The grant names the 17, and the sequences it needs are named too, because two
sequences in the live database (`materials_material_id_seq`,
`services_service_id_seq`) belong to reserved tables. `ON ALL TABLES` and `ON
ALL SEQUENCES` would have handed the running service full write access to all
six, and the ability to advance two counters it has no use for.

The alternative was considered and rejected: granting `SELECT` on all tables and
restricting only writes. It is simpler, and it leaves the reserved tables
readable by a credential that has no reason to read them.

**No privilege on the reserved tables is not a bug that will be fixed when those
features are built.** When one is built, the table gets a model, and the grant
list grows by exactly that table, in the same commit as the model. The
alternative — granting DML on tables the application does not model, in advance —
is the "allow everything now, restrict later" shape that stays unrestricted,
because nothing later ever re-audits it.

## Reachability is enforced by `pg_hba.conf`, not by REVOKE

The application role must not be able to connect to another application's
database on the same instance. Two things are commonly confused here, and only
one of them works.

**`REVOKE CONNECT ... FROM PUBLIC` does not do this.** The revocation is *per
database*. It does not make the server-wide; it makes that one database
unreachable to everyone relying on the default, while every other database keeps
its `PUBLIC` CONNECT unchanged. An application that has run it and believes it
is isolated is not.

It is also someone else's change to make. Revoking `PUBLIC` on a database this
project does not own breaks whichever tenant depends on the default, from code
that has never heard of this file.

**`pg_hba.conf` does do this.** It is evaluated before any SQL runs, applies
across every database at once, and is scoped to a single role:

```
# TYPE     DATABASE     USER               ADDRESS        METHOD
host      <database>   <runtime>_app      <app-cidr>     scram-sha-256
host      all          <runtime>_app      0.0.0.0/0      reject
```

The deny-all line must come *after* the allow line — `pg_hba.conf` is
first-match — and both must sit above any broader rule already present. Reload
rather than restart so in-flight connections survive.

Step 4 of the SQL file gives the commands to locate the file, insert the rule
above the existing broader lines, and reload. Do not skip the verification: until
a cross-database connection has actually been observed to be rejected, the
isolation this directory is credited with does not exist yet.

## Before running

- Replace every `<placeholder>`. Do not leave a literal in place.
- Check the names are free, or you will collide with another application:

  ```bash
  docker exec -it <pg-container> psql -U <admin-user> -c '\du'
  docker exec -it <pg-container> psql -U <admin-user> -c '\l'
  ```

- Generate real passwords (`openssl rand -base64 32`). Never write a password
  into a file in this repository, or into a compose file. `.env` is gitignored;
  confirm it stays that way.
- Read the instance inventory (`SELECT datname, datacl FROM pg_database;`) so you
  know what currently relies on the `PUBLIC` default before changing anything.
  A `NULL` `datacl` means "default".

## After running

The SQL file ends with verification queries, commented out because they are
checks rather than steps. Run them, the privilege tests **as `<runtime>_app`**.

| Check                                        | Expected |
|----------------------------------------------|----------|
| no capability attributes on the role         | 0 rows   |
| role owns no tables                          | 0 rows   |
| role `SELECT`                                | succeeds |
| role `INSERT` (then roll back)               | succeeds |
| role `CREATE TABLE`                          | fails    |
| role `DROP TABLE`                            | fails    |
| role `ALTER TABLE ... ADD COLUMN`            | fails    |
| role `CREATE INDEX`                          | fails    |
| role connecting to another app's database    | fails    |

The last one is the one to actually run from a different host. A permission
error rather than a connection rejection means the `REVOKE` ran but
`pg_hba.conf` did not take effect — the SQL file's step 4 is the fix.

A check that succeeds where it was expected to fail means the role has more
privilege than intended. Fix it before pointing the application at it.

## Not automated, on purpose

- No `CREATE DATABASE` in the SQL file. The database is created empty by an
  administrator and then populated from the schema of record, so the schema
  always has exactly one source.
- No idempotency guards beyond the statements themselves. This is a short,
  reviewable, human-run file; it is not a deployment artifact. If it needs
  re-running, drop the role first and start again.
- No password generation in the script. A password generated by a script ends up
  in a compose file or a log.
- No provisioning of a second role. See above; a DDL role that does not own the
  schema cannot do DDL, and one that does own it defeats the boundary.

## Relationship to the sibling project

A sibling application shares this PostgreSQL instance and has its own
provisioning file. The two are independent, and neither creates the other's
objects. They agree on two points, both of which are properties of the instance
rather than of any one application:

- the application role holds DML only, and ownership is never transferred to it
- reachability is enforced with `pg_hba.conf`, not with `REVOKE ... FROM PUBLIC`

The sibling's own documentation carries the same `pg_hba.conf` warning, which is
the reason this file cites it rather than substituting a grant for it.

## See also

- `docs/deployment-guide.md` §2 for the operational sequence.
- `ai-specs/skills/deploying-backend-vps/SKILL.md` for the general procedure;
  this directory is a concrete instance of it.
