# Step 13 — Unit tests and database verification

Date: 2026-10-02
Database compared: `db_gestiket_acme` (this project's own, on the shared core)
Bucket compared: `app-tickets-local-uploads` (this project's own)
Role used for the baseline: `gestiket_app` (this project's own, DML only)

## 13.1 Baseline, read through this project's own role

The baseline is read as `gestiket_app` on purpose. That role can see 17 of the 23
tables and cannot read `alembic_version`, `uom`, `holidays`, `materials`,
`preliquidated` or `services`. A baseline taken with a broader credential could
have compared another tenant's rows and reported them as this project's.

```
database = db_gestiket_acme
role     = gestiket_app
adticketswkd               0      labsdls                   0
cancellations              0      maintenances              0
equipments                 2      maintenances_spares       0
fsm_users                  1      maintenances_technicians 0
markets                    2      pauses                    0
photos                     0      spares                    0
technicians                1      tickets                   0
token_blacklist            0      uploads_sessions          0
worksheets                 0
```

`alembic_version` read separately through the elevated credential the migrate job
uses: `0003_join_table_keys`.

## 13.2 Targeted tests

```
venv/bin/python -m pytest tests/test_local_assets.py tests/test_env_collection_settings.py \
  tests/test_minio_endpoints.py tests/test_deploy_assets.py -v
```

**138 passed**, 1 warning (`passlib` on the stdlib `crypt` module).

## 13.3 Full suite with coverage

```
venv/bin/python -m pytest -v --cov=app --cov-report=term-missing
```

**705 passed, 1 skipped**, 1 warning. `TOTAL 1972 statements, 144 missed, 93%`.

The one skip is pre-existing and unrelated to this change.

> Final counts, re-measured after the photo-residue guard of 13.9 was added and
> confirmed at 16.1: **138 passed** on the targeted cross-suite run above, and
> **706 passed, 1 skipped** on the full suite. §13.3 above records the run made at
> the time this section was written, before that last guard existed; the two
> figures differ by exactly that one test.

## 13.4 Baseline after the gate

`make gate-local` exit 0, then the baseline re-read and diffed against 13.1:

```
IDENTICAL — no row changed, nothing accumulated
```

The gate creates a ticket, a maintenance, an upload session, an object and a
photo row, and removes all five. This was not true when this step was first run:
`photos` grew by one on every run, because completing an upload inserts a
`photos` row whose `maintenance_id` is NULL — the service stores the path but
does not attach the row to its parent — so `DELETE /maintenances/{id}` cannot
reach it and the foreign key is NO ACTION. The gate now removes those rows,
scoped by the ticket id inside the stored path. Three consecutive runs after the
fix left the table unchanged.

Bucket after the gate: **0 objects**.

## 13.5 The gate does not migrate

`alembic_version` before and after: `0003_join_table_keys`, unchanged. The gate
runs no migration; it reads the revision only to print it.

## 13.7 Rebuild from scratch

This step found a defect that no test in the suite could find.

`make local-down`, then this project's own database, bucket and object-store user
dropped **by name**, then `make setup-local`:

| Dropped | Object |
| --- | --- |
| database | `db_gestiket_acme` |
| bucket | `app-tickets-local-uploads` |
| object-store user | `gestiket_app` |

Two idle sessions had to be terminated first — both were this project's own
`gestiket_app`, left behind by the removed API container. PostgreSQL keeps a
backend until it notices the client is gone.

The first from-scratch attempt failed with `relation "adticketswkd" does not
exist`. The local setup applied the provisioning template **before** the schema,
while the template grants on tables by name and migration `0001` adds
`token_blacklist`. It only ever passed on a machine whose database happened to be
populated already.

The quieter half of the same defect is worse. `ALTER DEFAULT PRIVILEGES` sits
above the failing `GRANT` in the template, so the failed run still left a default
ACL granting `SELECT, INSERT, UPDATE, DELETE` on every future table. The next run
loaded the schema, and all 23 tables inherited it — including the six the
template exists to withhold. `gestiket_app` could read `uom`, `alembic_version`,
`holidays`, `materials`, `preliquidated` and `services`, and no step reported
anything.

Fixed by ordering the steps the way the template documents: database → schema →
migrations → provisioning → seed. Verified afterwards:

```
17 of 23 tables grantable
alembic_version=f  holidays=f  materials=f
preliquidated=f  services=f    uom=f
```

Guards added for both halves: `test_grants_are_applied_after_the_schema_and_migrations`
and `test_local_setup_never_grants_more_than_the_canonical_template_lists`. The
first was mutation-checked by moving provisioning back before the schema.

## 13.8 Nothing else on the core changed

State captured before the rebuild and again after the gate, from outside this
project's containers:

| Object | Before | After |
| --- | --- | --- |
| `catalog_db` | present | present |
| `db_gci_acme` | present | present |
| `postgres` | present | present |
| `provider-portal` | present, 0 objects | present, 0 objects |
| `tecfrio-uploads-own-api` | present, 5 objects | present, 5 objects |
| `tecfrio_access_key` | `policyName=tecfrio-app`, `updatedAt=2026-10-01T02:29:40Z` | identical |
| `postgres-gci` | up 9h (healthy) | never restarted |
| `minio-acme` | up 9h | never restarted |

The only difference in the whole capture is this project's own
`gestiket_app.updatedAt`, because that user was deliberately dropped and
recreated as part of 13.7.

## Defects this step found

All were found by running the stack. Each is now covered by a test, and each of
those tests was mutation-checked by reintroducing the defect and confirming the
test fails.

| Defect | Consequence | Guard |
| --- | --- | --- |
| Template applied before the schema | from-scratch setup fails | `test_grants_are_applied_after_the_schema_and_migrations` |
| Grants skipped when the role exists | role with no privileges; login 500 | `test_provisioning_reapplies_grants_when_the_role_already_exists` |
| Token declared `local` | gate aborts at the first write | `test_gate_uses_a_token_every_later_check_can_reach` |
| Enum values lowercased | `POST /tickets` 500 | `test_gate_writes_enum_labels_the_schema_actually_declares` |
| Synthetic upload parent | `uploads/complete` 404 | `test_gate_uploads_against_a_parent_row_that_exists` |
| Presigned URL used as the object key | one object leaked per run, as a warning | `test_gate_removes_the_uploaded_object_by_key` |
| Trap behind `[ -t 1 ]` | no failure summary in CI | `test_gate_reports_failure_and_cleans_up_without_a_tty` |
| `cleanup()` never called | failed run broke the next one | same |
| Hex-only revision pattern | `unknown revision` on a healthy database | `test_no_local_script_matches_revisions_by_the_shape_of_a_hex_id` |
| Migrate env not exported | migrate job started with no settings | `test_both_local_scripts_share_one_migration_environment_helper` |
| Photo rows never removed | one row per run, forever | `test_gate_removes_the_photo_rows_the_upload_leaves_behind` |
| Public origin required to differ from internal | gate rejected correct local config | — (see below) |

The last one is a rule that was wrong rather than missing: it asserted the
presigned URL's host must differ from `MINIO_ENDPOINT`, which is true on the VPS
where the internal name resolves nowhere, and false locally where MinIO is
published on loopback and a client genuinely resolves it. It now only applies the
check when the two differ, which is the case that indicates a defect.

## Not verified here

`TICKET-019` records 94 model operations stale against the schema, so no local run
can assert that the models and the schema agree. `etl/seed_db.sh` emits a
non-fatal fidelity-check `syntax error at or near "SELECT"` after loading all five
seed tables; `etl/**` is outside this change and the defect is recorded in task
17.5.
