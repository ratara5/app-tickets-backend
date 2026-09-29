# TICKET-022: the provisioning script claimed isolation and a DDL role it could not deliver

- **Status:** Resolved
- **Severity:** High — a shared-instance isolation claim that did not hold, shipped as doctrine
- **Owner:** ratara5
- **Review by:** 2026-12-27
- **Related:** `TICKET-018`, `TICKET-021`, `ai-specs/skills/deploying-backend-vps/SKILL.md`

## Problem

`deploy/provision/001-create-application-roles.sql` and the deployment skill, both
added for the shared-instance rollout, made two claims that did not survive
verification.

### 1. The migration role could not do migrations

The script provisioned two roles:

| Role            | Granted                       | Stated purpose              |
|-----------------|------------------------------|-----------------------------|
| `<runtime>_app` | `USAGE` on schema, DML       | the running service         |
| `<runtime>_migr`| `USAGE, CREATE` on schema    | running a migration         |

In PostgreSQL, `GRANT CREATE ON SCHEMA` permits creating **new** objects. `ALTER`
and `DROP` on **existing** ones require **ownership**, and the same script
deliberately never grants ownership to any application role. So the migration role
could create an empty table and could not alter a real one. It could not do the
job it existed for.

The test suite appeared to prove the opposite, and this is the part worth
remembering: the behavioural check created a table *as the migration role* and
then altered that table. The role was altering a table it had just created itself.
Every assertion passed, and the design was still broken.

### 2. `REVOKE CONNECT ... FROM PUBLIC` was described as server-wide, and is not

The script revoked `CONNECT` from `PUBLIC` on `postgres` and `template1`, and the
README and skill called this a server-wide change that establishes isolation from
other tenants.

`REVOKE` is **per database**. It does not make the server-wide. It makes that one
database unreachable to any tenant relying on the default, and it leaves every
other database on the instance exactly as reachable as before. An application that
has run it and believes it is isolated from its neighbours is not.

The cross-database test passed for the same reason the first one did: it
hand-revoked `sibling_app` before asserting the role could not reach it, so the
test proved the hand-written revoke, not the script.

Both of these are worse than the omission they replaced, because each was a
security boundary described in prose that an operator would act on.

## Resolution

Following the convention the sibling project settled on, which is also the
simpler one: **one role, and the administrator owns the schema.**

### 1. The migration role is removed

Schema change belongs to whoever owns the schema, run by hand, the same way the
schema of record is loaded. There is no second role and no second credential.

The two ways to make a DDL role work were both rejected as worse than the
defect:

- **Transfer table ownership to it.** The credential that exists to reshape the
  schema then owns the data, and the owner/grantee distinction the whole file
  rests on is gone.
- **Grant it to the runtime role.** The service credential inherits every DDL
  capability, which is precisely what the split existed to prevent.

`0001_baseline` already needed the administrator's credentials to stamp, so
nothing about the migration path actually required a role.

The skill and the `migrate` job target both say so explicitly, and the compose
`migrate` service no longer inherits `env_file` — an elevated credential is now
passed by hand rather than being a default in the same file that configures the
running service.

### 2. Isolation is enforced with `pg_hba.conf`

```sql
host    <app_db>   <app_role>   <app-cidr>    scram-sha-256
host    all        <app_role>   0.0.0.0/0     reject
```

Evaluated before any SQL, applies across every database at once, and scoped to
one role. It cannot affect a tenant this project has nothing to do with, which is
the property the old approach was missing. First-match ordering is called out,
since reversing the two lines locks the role out of its own database and presents
as a broken grant rather than a broken rule. Reload, not restart.

### 3. A broken verification query

The ownership check asked `information_schema.tables` for `tableowner`, a column
that does not exist. It errored, and the error was filed under "checks that are
expected to fail", so the one query that mattered most — does the application role
own anything — was never established. Corrected to `pg_tables`, and a guard added
so the catalog and the column cannot drift apart again.

## Guards

`tests/test_provisioning.py` — 35 checks, up from 23. Verified by mutation: each
of the following was introduced and each was caught.

| Mutation                                        | Caught by |
|-------------------------------------------------|-----------|
| re-add `<runtime>_migr`                          | `test_no_migration_role_is_provisioned`, `test_creates_exactly_one_role` |
| `GRANT USAGE, CREATE` to the app role            | `test_no_role_receives_create_on_the_schema` |
| `ALTER ... OWNER TO`                              | `test_no_statement_moves_or_shares_ownership` |
| `ALTER DEFAULT PRIVILEGES FOR ROLE <app_role>`   | `test_default_privileges_name_the_owning_role_not_the_app_role` |
| re-add `REVOKE CONNECT ... postgres FROM PUBLIC` | `test_does_not_revoke_connect_from_public_on_system_databases` |
| reverse the `pg_hba` allow/deny order            | `test_pg_hba_is_documented_with_allow_before_deny` |
| drop `NOINHERIT`                                 | `test_noinherit_is_set_explicitly` |
| ownership check against `information_schema`     | `test_the_ownership_check_uses_a_catalog_that_has_the_column` |

Two of the original tests were themselves wrong and have been rewritten:

- `test_the_role_is_not_created_with_a_privileged_attribute` compared
  `attribute not in options`, and `NOSUPERUSER` contains `SUPERUSER`. It passed
  over the very declaration it was written to catch. Now a token-boundary check
  plus a positive assertion that each `NO…` is stated explicitly.
- `test_isolation_is_documented_as_per_database_not_server_wide` cannot simply ban
  the phrase, because the file has to name the misconception in order to correct
  it. Every line using it must now also deny it.

## Verification

Proven on a disposable PostgreSQL 16 instance built from `deploy/schema.sql`
(23 tables, 7 sequences), with the template rendered to real names:

| Check                                        | Result |
|----------------------------------------------|--------|
| no capability attributes on the role         | pass — 0 rows |
| role owns no tables (`pg_tables`)            | pass — 0 rows |
| `has_schema_privilege` USAGE / CREATE        | pass — `true` / `false` |
| `CREATE TABLE`                               | denied |
| `DROP TABLE`                                 | denied |
| `ALTER TABLE ... ADD COLUMN`                 | denied |
| `CREATE INDEX`                               | denied |
| `TRUNCATE`                                   | denied |
| `SELECT`                                     | succeeds |
| `INSERT`, `DELETE`                           | succeed |
| `nextval` on an existing sequence            | succeeds |
| table created later by the admin, as the role | DML auto-granted (`true`/`true`) |
| its new sequence                             | auto-granted (`true`) |

The `ALTER DEFAULT PRIVILEGES FOR ROLE` mutation was also run end to end on a
second instance. Naming the app role instead of the owner leaves a table created
afterwards with no privileges for it (`false`), while the 23 pre-existing tables
remain correctly granted — the exact silent failure the `<admin>` placeholder
guard exists to prevent, since the script applies without error in both cases.

## Notes

- The behavioural matrix now runs the privilege checks **as the role** rather than
  as the administrator, which is the only way the DDL denials mean anything.
- The cross-database check is required from a different host, not over loopback:
  the `pg_hba` rule is address-scoped, and a loopback test exercises a different
  code path than a misconfigured peer would.
- The skill no longer claims a DDL role exists, and the shared doctrine documents
  the `pg_hba` mechanism as the one that enforces reachability, with a warning
  about the test that flatters the two-role design.
