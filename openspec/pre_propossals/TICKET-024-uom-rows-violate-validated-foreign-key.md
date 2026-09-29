# Defect: two live `uom` rows violate a validated foreign key

## Metadata

- **Summary**: `uom.ref_unit` carries a self-referencing foreign key that PostgreSQL reports as validated, yet two live rows point at a `ref_unit` that does not exist, so the constraint is not actually in force
- **Issue Type**: Data Integrity Defect
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: database, data-integrity, reserved-table, seed
- **Owner**: ratara5
- **Review date**: 2027-01-27, aligned with TICKET-018

## Description

`uom` is one of the five tables kept for unbuilt features and deliberately has no
ORM model (TICKET-018). It is also the table the TICKET-021 widening changes.

The live table declares:

```
uom_ref_unit_fkey  validated=true  FOREIGN KEY (ref_unit) REFERENCES uom(unit)
```

`convalidated` is `true`, which is PostgreSQL's record that every existing row
satisfies the constraint. That record is wrong. Two rows do not:

```
cilindro         -> ref_unit=lb
medio cilidndro  -> ref_unit=lb
```

There is no `lb` unit in the table. The full unit list is `cilindro`, `gal`, `kg`,
`l`, `m`, `medio cilidndro`, `par`, `rollo`, `u`.

```
SELECT u.unit, u.ref_unit
FROM uom u
WHERE u.ref_unit IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM uom p WHERE p.unit = u.ref_unit);
```

A validated foreign key cannot be created while violating rows exist, so the rows
were written while the constraint was absent, or while triggers were disabled. The
constraint was then validated in a state that should have been impossible, which
means the validation did not do what it claims to have done.

## Impact

- **The constraint does not protect the column.** Anything that writes `uom` today
  is governed by a rule the data already breaks. `lb -> kg` is the canonical
  conversion factor, `0.45359237`, and the unit it belongs to is the one missing
  from the table. That is the same value the TICKET-021 widening exists to store
  exactly, so the ticket that fixes precision is the ticket whose data is broken.
- **Re-loading `uom` will fail.** `etl/seed_db.sh` inserting these rows through
  normal DML raises:

  ```
  ERROR:  insert or update on table "uom" violates foreign key constraint "uom_ref_unit_fkey"
  DETAIL:  Key (ref_unit)=(lb) is not present in table "uom".
  ```

  This is reproducible without touching live. Building a database from
  `deploy/schema.sql` and copying live's rows fails the same way, because
  `deploy/schema.sql` is generated from live and carries the constraint too. It is
  also why the rehearsal for TICKET-021 had to `ALTER TABLE uom DISABLE TRIGGER
  ALL` before it could load the rows.
- **Nothing in the application notices**, because nothing reads `uom`. The feature
  it backs was never built.

## Reproduction

```bash
docker exec postgres-gci psql -U postgres -d db_gestiket_acme -c "
SELECT conname, convalidated, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conrelid='uom'::regclass AND contype='f';"

docker exec postgres-gci psql -U postgres -d db_gestiket_acme -c "
SELECT u.unit, u.ref_unit
FROM uom u
WHERE u.ref_unit IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM uom p WHERE p.unit = u.ref_unit);"
```

## Resolution options

Not decided here. The three candidates, in the order I would try them:

1. **Insert the missing `lb` unit** and correct the two `ref_unit` values. This
   makes the data satisfy the constraint that live already claims is enforced, and
   it is the only option that leaves the factor `0.45359237` loadable. It needs a
   decision on `lb`'s `magnitude` and whether `factor_conversion` is a
   self-ratio (`lb -> lb = 1.00`, as every other row is) or a ratio to `kg`
   (`0.45359237`). Every other row in the table is a self-ratio, so the first
   reading is consistent with the data and the second is the one that makes the
   number mean something.
2. **Add the `lb` unit and set both `ref_unit` values to a unit that exists.** Same
   repair, less useful, and it discards the information that these units were
   measured against pounds.
3. **Drop `uom_ref_unit_fkey`.** This removes a rule rather than satisfying it,
   and is only defensible once the feature that needs `uom` is designed, because
   the column's meaning is what the constraint was documenting.

The `medio cilidndro` spelling in one of the two rows is a separate typo, tracked
in TICKET-018. Fixing the spelling and repairing the foreign key in one change
would make the repair harder to review, so they are deliberately kept apart.

## Notes

- Found while rehearsing the TICKET-021 migration on a throwaway database, not by
  reading live schema. `alembic check` cannot see it: `uom` is excluded from
  autogenerate as a reserved table, so nothing compares its constraints, and
  autogenerate does not validate constraints against data in any case.
- `deploy/schema.sql` inherits the defect, because it is generated from live. A
  fresh environment built from the dump has the same constraint and the same two
  bad rows, so the failure reproduces there too.
- The rehearsal database used for TICKET-021 was dropped after the round trip.
- Read-only inspection. `postgres-gci` was not stopped, restarted or reconfigured.

## Escalation 2026-09-29 — this breaks disaster recovery, not just the loader

Taking the pre-migration backup for TICKET-021 exposed a worse consequence than
the loader failing. `pg_dump` emits `COPY` statements *before* it emits
`ADD CONSTRAINT`, so a restore loads all the data with the foreign keys not yet
in place and creates them at the very end. The three violating rows are therefore
present when the constraints are finally added, and the `ALTER TABLE` fails:

```
psql:<stdin>:2274: ERROR:  insert or update on table "spares" violates foreign key constraint "spares_unit_fkey"
psql:<stdin>:2330: ERROR:  insert or update on table "uom" violates foreign key constraint "uom_ref_unit_fkey"
```

The consequences are worse than the error itself:

- **Neither constraint exists in the restored database.** Verified by querying
  `pg_constraint` after the restore: both names are absent.
- **`psql` exits 0.** The restore reports success. Only reading stderr reveals
  it, and `ERROR` does not start the line — it is prefixed with
  `psql:<stdin>:2274:`, so a `grep '^ERROR'` misses every one of them. That is
  how this was nearly missed during the window: the first attempt appeared clean.
- **All 23 tables and all data restore correctly.** Row counts match live
  exactly for `uom`, `spares`, `tickets`, `photos`, `maintenances`, `fsm_users`
  and `worksheets`. Nothing else is wrong.

So a disaster recovery today would restore a database that is missing two
referential-integrity constraints and would tell the operator it succeeded. The
instant the container is restored and something writes `spares.unit` or
`uom.ref_unit`, the constraint that was supposed to stop it is not there.

This is now documented in
`ai-specs/skills/deploying-backend-vps/SKILL.md` Phase 5 gate 2: a backup is not
proven until it has been restored, and the check is a constraint count plus a
grep that does not assume errors start at the beginning of a line.

### The second violation is the TICKET-018 typo

`spares.spare_id = 411` (`Gas nitrogeno X 5.0 M3`) has
`unit = 'medio cilindro'` — the correct spelling. `uom` stores
`medio cilidndro`, with the typo. So the `spares` row is right and the `uom` row
is wrong, and the typo is what breaks the constraint.

That ties this ticket to TICKET-018 tightly, and it argues for fixing the two
together after all: the spelling fix repairs `spares_unit_fkey` on its own, and
adding the missing `lb` unit repairs `uom_ref_unit_fkey`. Both repairs are data
changes to `uom`, which currently has no writer.

A full inventory of every foreign key in live was taken as part of this: 38
checked, exactly 3 violating rows, all three pointing into `uom`. Nothing outside
`uom` is affected, so the blast radius is one reserved table and the recovery
path.

### Recommended order

1. Add the `lb` unit, with `factor_conversion` decided: a self-ratio `1.00`,
   consistent with all 9 existing rows, or `0.45359237` as lb to kg. The widened
   column now stores either exactly. Note that `0.45359237` is only meaningful as
   a conversion to a *reference* unit, so this depends on whether `ref_unit` is
   meant to be "the unit this is measured against" — the other 9 rows being
   self-ratios suggests the column is used two different ways and the design
   needs a decision before the value is chosen.
2. Correct `medio cilidndro` to `medio cilindro` (TICKET-018). This repairs
   `spares_unit_fkey` and removes a typo from user-visible reference data.
3. Re-take the backup and prove the restore: zero errors, 38 foreign keys present.
4. Only then treat disaster recovery as working.

## Resolved 2026-09-29

Both repairs applied to live in one transaction, and disaster recovery re-proven.

### The `lb` decision

`factor_conversion` reads as **how many `ref_unit` per 1 `unit`**, which the
existing rows confirm exactly: the five base units (`kg`, `l`, `m`, `rollo`, `u`)
are self-ratios at `1.00`, and the derived units point at a base (`gal`→`l` 3.79,
`par`→`u` 2.00, `cilindro`→`lb` 40.00, `medio cilindro`→`lb` 20.00).

So `lb` is a **missing base unit**, not a missing derived one, and it gets a
self-ratio like the others:

| unit | magnitude | uom_description | ref_unit | factor_conversion |
|---|---|---|---|---|
| `lb` | `masa` | `libras` | `lb` | 1.00 |

`magnitude` is a category, not a number — `masa`, `volumen`, `longitud`,
`unidad`, `rollo` — and descriptions are plural, so `libras` matches `kilogramos`.
`0.45359237` was **not** used, for a structural reason worth recording:

**`uom.unit` is the primary key, so a unit can have exactly one row.** `lb` can
therefore be self-referential (`1.00`) *or* expressed against `kg`
(`0.45359237`), never both. Storing the lb→kg factor would have meant deleting
the `lb` row that `cilindro` and `medio cilindro` depend on. The self-ratio is
the only non-destructive choice.

This is a genuine limitation of the table's design, not of this ticket: the
widen in TICKET-021 gives precision room, but with `unit` as the PK that room is
unreachable for a unit that already has a self-ratio. A unit whose only
relationship is to a base cannot be expressed. Fixing it means a composite
primary key on `(unit, ref_unit)`, which is a schema change and a TICKET-018
design decision, deliberately **not** taken here. The widening is still correct —
it prevents silent rounding of whatever factors are stored — but the motivating
lb→kg example is not loadable into this table as designed.

### The typo

`UPDATE uom SET unit='medio cilindro' WHERE unit='medio cilidndro'`, safe
because nothing referenced the misspelled key. Corroborated by the row's own
`uom_description`, which already read `medios cilindros` — only the key was
transposed, so the description was the source of truth for the intended value.

No committed source reintroduces it: `etl/data/` holds only `.gitkeep`, so the
typo lived in live data alone.

### Disaster recovery re-proven

A single-database `pg_dump` (not `pg_dumpall`, which carries `CREATE DATABASE`
and `\connect`) was restored into a fresh empty database:

- **0 errors**, not anchored to `^ERROR`, which misses all of them.
- All 38 foreign keys present, both previously-dropped ones included, with
  `convalidated=true`.
- All 23 table row counts identical to live.
- `uom` carries the repair: `lb` present, typo absent.
- `alembic_version` survives with `0002_widen_uom_factor`.

Live is at baseline plus exactly the intended change: `uom` 9→10 rows.

## Incident during this work — how the missing primary keys caused data loss

The first restore attempt used the full-instance `pg_dumpall` file against the
running server. `CREATE DATABASE` failed with "already exists", so the script
`\connect`ed to the **live** database and began inserting its rows into it.

20 of 23 tables were protected by a primary key and rejected the duplicates with
errors. **`mantenimientos_repuestos` and `mantenimientos_tecnicos` were not.** They
have no primary key in live — the TICKET-019 finding — so nothing rejected their
rows and both tables doubled: 3→6 and 5→10. The restore was writing into the
operational record of a system the user is actively testing.

Detected within one step, by diffing exact row counts against the pre-work
baseline, and repaired by deleting the 8 injected rows by `ctid` (they were exact
copies; the originals had the lower `ctid`). All 23 tables verified back to
baseline, contents inspected row by row.

Two lessons, both now encoded:

1. **A restore drill must not target the running server.** Use a single-database
   `pg_dump` and a fresh empty database. `pg_dumpall` is for rebuilding an
   instance, not for testing a restore, and against a live instance it fails
   open into the wrong database.
2. **The tables with no primary key are exactly the ones a restore corrupts
   silently.** This raises the priority of the TICKET-019 live-side work: adding
   those two primary keys is not cosmetic, it is the difference between a failed
   restore being loud and being silent.
