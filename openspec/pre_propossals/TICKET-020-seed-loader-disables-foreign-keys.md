# Bug: the seed loader disables foreign keys and reports success even when the load fails

## Metadata

- **Summary**: `etl/seed_db.sh` runs `COPY` under `session_replication_role = 'replica'`, which disables constraint triggers for the load, then prints a success line unconditionally and without `ON_ERROR_STOP`
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: High
- **Labels**: backend, database, deployment, data-integrity
- **Owner**: ratara5
- **Discovered**: 2026-09-26, while measuring the live state of the reserved tables for `TICKET-018`

## Description

`etl/seed_db.sh:96-105` loads each CSV like this:

```bash
docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -c \
  "SET datestyle = 'DMY';
  SET session_replication_role = 'replica';
  COPY \"$table\" FROM '$container_path' WITH (FORMAT csv, HEADER true, NULL '');
  SET session_replication_role = 'origin';
  SET datestyle = 'ISO, MDY';"

success "Loaded: $filename → $table"
```

Two independent defects, both of which make a bad load look like a good one.

**1. Referential integrity is switched off for the duration of the load.**
`session_replication_role = 'replica'` disables constraint triggers. Any foreign key
in the target schema stops being enforced, so orphan rows load silently and stay.
The script never re-checks integrity after restoring `'origin'`.

**2. The success line is unconditional.** There is no `-v ON_ERROR_STOP=1`, and all
five statements are passed to a single `psql -c`, so PostgreSQL runs them as one
implicit transaction. If the `COPY` fails, the batch aborts, `psql` still exits
without a fatal error the script can detect, and `success "Loaded: ..."` prints
anyway. The `SET session_replication_role = 'origin'` is skipped too; the
connection closing resets it, so the session does not leak — but the report is a lie.

This is the exact failure mode `docs/learned-lessons.md` §5 warns about, in the
project's own script: *a command that "works" because errors scroll past*.

## This is not hypothetical — it is why `uom` is inconsistent

Measured on the live database, `spares_unit_fkey` is **validated** (`convalidated = t`)
with `NO ACTION` on update and delete. That combination cannot produce an orphaned
child through normal DML. Yet:

- one `spares` row references `medio cilindro`, which does not exist in `uom`;
- `uom` instead holds `medio cilidndro` — a transposed typo — referenced by nothing.

A validated `NO ACTION` constraint would have rejected both states. The load path
in `etl/seed_db.sh` explains it: the rows arrived while constraint triggers were
disabled, and nothing has looked at them since. The full `uom` breakdown is in
`TICKET-018`.

So the loader is not merely untidy. It is the reason a live database can hold data
that its own constraints forbid, and the reason nobody found out.

## Impact

- The live database's referential integrity is unverified, and at least one real
  violation already exists.
- A failed seed presents as a successful seed. The operator proceeds to
  configuration, credentials and `uvicorn`, and discovers the problem only when a
  feature reads a table that was never populated.
- Every future seed run repeats the exposure. The only guard is the row-count check
  at `etl/seed_db.sh:87`, which protects against re-loading a populated table but
  says nothing about whether the load was correct.

## Reproduction

```bash
# A CSV whose FK column points at a non-existent parent
printf 'spare_id,spare_name,unit,price\n999,probe,no_such_unit,1.00\n' > /tmp/bad.csv
# load it through the script's COPY statement and observe: no error,
# `success "Loaded"`, and a row violating a validated foreign key.
```

## Acceptance criteria

- [ ] `psql` is invoked with `-v ON_ERROR_STOP=1` and the script aborts on a failed
      `COPY`, with no success line printed.
- [ ] The success line reflects the actual outcome of the load, not the fact that
      the command was issued.
- [ ] `session_replication_role` is scoped as tightly as possible. If the load
      genuinely needs triggers off, the intent is stated, the bypass is
      per-table rather than global, and a post-load integrity check validates every
      foreign key in the affected tables and fails the run.
- [ ] Foreign keys are not disabled at all where ordering the input correctly makes
      them unnecessary. `replica` is a last resort, not the default.
- [ ] A verification query runs after the load and compares the loaded row set
      against the file, rather than relying on a command's exit status.
- [ ] The existing `medio cilindro` / `medio cilidndro` violation is resolved
      (tracked in `TICKET-018`).

## Notes

- The script does guard against one thing correctly: it refuses to load into a
  non-empty table (`etl/seed_db.sh:86-94`), which is a sensible safety property
  worth keeping.
- `docker exec "$DB_HOST" psql ... -tAc "SELECT COUNT(*)"` at
  `etl/seed_db.sh:87` is a bare count, so it cannot distinguish "loaded 0 rows
  because the file was empty" from "the file was never found". Comparing the row
  set against the file's line count would be the stronger check.
- Related: `TICKET-018` (the reserved tables this defect corrupted),
  `TICKET-019` (the models do not even declare the `spares.unit` foreign key that
  exists in the live database, so a freshly built database would have no constraint
  to violate here at all).

## Resolution

**Resolved 2026-09-27 by removing the bypass entirely, not by ordering around it.**

`session_replication_role = 'replica'` is gone. It was never a last resort that
ordering made unnecessary; it was the mechanism, and it was the only reason a bad
reference could reach the database unnoticed.

What replaced it, and why each part was necessary:

- **Ordered, transactional loads with constraints on.** Every COPY runs inside
  `BEGIN`/`COMMIT` with `ON_ERROR_STOP=1`, in an explicit parent-before-child
  order. A dangling reference now aborts and rolls back.
- **A staging pass for the one genuine cycle.** `uom.ref_unit -> uom.unit` is a
  unit pointing at its own base unit, so a derived unit can legitimately appear
  above its base in the file and no ordering of that file satisfies the
  constraint. `uom` loads into a TEMP table and is then inserted in passes, a row
  going in only once its parent exists. Rows that remain unresolved mean a
  dangling or circular reference, and the load fails.
- **A post-condition that proves the result.** One left-join orphan count per
  outgoing foreign key of every loaded table, failing the run on any non-zero
  count. Nothing verified the outcome when triggers were disabled; now the
  script has to demonstrate it.

Two findings worth recording, because both are the kind that survive a rewrite:

1. **`DEFERRABLE INITIALLY DEFERRED` was the wrong fix, and nearly shipped.**
   Deferring `uom_ref_unit_fkey` for the load transaction is the textbook answer
   and it worked: children before parents loaded fine. It was rejected because
   PostgreSQL refuses to restore `NOT DEFERRABLE` while deferred trigger events
   are still pending, so the constraint was left **permanently deferrable**. A
   data script would have silently changed the schema of record. The staging
   approach reaches the same result with no DDL at all.

2. **The five "reference" tables are not all reference data.** `materials` and
   `services` have `maintenance_id` foreign keys to `maintenances`, and
   `preliquidated.ticket_id` is `NOT NULL` and references `tickets`. They are
   line items on a live record, so loading them needs business rows to exist
   first. The loader now splits the two classes and refuses business tables
   without `--allow-business-data`.

Scope, and one risk that was larger than the reported defect:

- A CSV's filename becomes its table name, so dropping `tickets.csv` into the
  data folder would `COPY` straight into the live `tickets` table, with
  constraints disabled, against whatever `--db-name` it was handed. The load is
  now behind an explicit allowlist, with `--dry-run` available to inspect the
  plan first.
- The existing `medio cilindro` / `medio cilidndro` violation is data, not code,
  and is still open in `TICKET-018`.

Verified on a disposable database built from `deploy/schema.sql`: a `uom` file
with children above parents loads and passes the orphan check; a `uom` file with
a `ref_unit` pointing outside the file is rejected with zero rows left behind;
and `uom_ref_unit_fkey` is still `deferrable=false, deferred=false` afterwards.
`tests/test_seed_loader.py` (14 static guards) prevents the bypass, the DDL, and
the allowlist from being reintroduced.
