# `services` is reserved for a services feature that was never built

## Metadata

- **Summary**: the live table `services` has no ORM model and backs a
  billable-services feature that was designed and never built; it is kept,
  unmodelled, until that feature is actually specified
- **Issue Type**: Reserved Table
- **Project**: app-tickets-backend
- **Priority**: Low
- **Labels**: database, reserved-table, technical-debt
- **Owner**: ratara5
- **Review date**: 2027-09-30, one year out rather than the 90 days used for live
  defects. This table is parked behind an unbuilt feature, so a 90-day review
  could only re-confirm that the feature is still unbuilt. Revisit when the
  feature is scheduled, not on a calendar.
- **Related**: TICKET-018 (the parent decision), TICKET-025, TICKET-026,
  TICKET-027, TICKET-029

## Description

`services` is one of the five tables TICKET-018 decided to keep for future
features. It holds no ORM model, deliberately, and `app/models/reserved.py` keeps
Alembic's autogenerate from proposing to drop it.

Live structure, read on 2026-09-30 from `db_gestiket_acme`:

| Column | Type | Notes |
|---|---|---|
| `service_id` | `integer` | **primary key**, serial via `services_service_id_seq` |
| `ticket_id` | `integer` | **no foreign key** — see below |
| `maintenance_id` | `uuid` | FK → `maintenances.maintenance_id`, `NO ACTION` |
| `service_description` | `text` | nullable |
| `qty` | `numeric` | **unscaled**, nullable |
| `price` | `numeric` | **unscaled**, nullable |

It holds **0 rows**.

## `services` and `materials` are the same unfinished design

Column for column, `services` is `materials` minus the `spare_id` foreign key:

```
         service_id  material_id     serial PK, same shape
         ticket_id   ticket_id       integer, no foreign key in either
    maintenance_id  maintenance_id   uuid FK to maintenances, NO ACTION
  *_description  *_description  text, nullable in both
             qty      qty    numeric, unconstrained, nullable in both
           price    price    numeric, unconstrained, nullable in both
```

The two tables are evidently a pair from one design, and they carry the same three
unsettled things:

1. **`ticket_id` has no foreign key** in either, while `maintenance_id` is
   properly constrained in both. Nothing prevents a row naming a ticket that does
   not exist, so the column is a free-text integer by accident rather than by
   decision.
2. **`qty` and `price` are bare nullable `numeric`.** For money this is a trap,
   and the project has already been bitten by it: TICKET-021 found
   `uom.factor_conversion` declared `numeric(5,2)`, unable to represent
   `0.45359237`, so it truncated to `0.45` and silently corrupted every
   conversion. These columns are the same shape of decision, waiting.
3. **The relationship to the parent is ambiguous.** Both tables carry *both*
   `ticket_id` and `maintenance_id`, and only one is constrained. A service line
   presumably belongs to a `maintenance`, in which case `ticket_id` should go.

That ambiguity is the reason `services` and `materials` are best settled
**together**, and why the one-ticket-per-table split required by TICKET-018 is a
filing convenience rather than a description of the work. TICKET-026 records the
same three points from the other side.

## Why no model was written

Per TICKET-018: a speculative model for an unbuilt feature is contradicted by the
real one, and a model in the codebase is far harder to remove than a table in a
script. Here a model would additionally have to pick between "services and
materials are one table" and "they are two", and that choice would then be baked
into the models, the schemas and the API.

## What must be decided when the feature is built

1. Are `services` and `materials` one table with a discriminator, two tables, or a
   table plus a view? Do not answer this table by table.
2. Does the parent link run through `ticket_id` or `maintenance_id`? If
   `maintenance_id`, `ticket_id` is dropped rather than constrained.
3. Explicit scale and nullability on `qty` and `price`, applying the TICKET-021
   lesson.
4. Whether `price` is unit price or line total. With a separate `qty`, the two
   are different, and the column name does not say which.

## Scope boundary

- No model. No migration. No change to the live database. No `DROP`.

## Acceptance criteria

- [x] The table has a ticket of its own, satisfying TICKET-018's per-table
      requirement. This is that ticket; it records no code change.
- [x] The overlap with `materials` (TICKET-026) is recorded, so the two are
      settled as one design rather than two.
- [ ] The feature is specified, and this ticket closes with it.
