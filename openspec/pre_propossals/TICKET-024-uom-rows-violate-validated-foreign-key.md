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
