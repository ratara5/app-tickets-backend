# `materials` is reserved for a materials feature that was never built

## Metadata

- **Summary**: the live table `materials` has no ORM model and backs a materials
  feature that was designed and never built; it is kept, unmodelled, until that
  feature is actually specified
- **Issue Type**: Reserved Table
- **Project**: app-tickets-backend
- **Priority**: Low
- **Labels**: database, reserved-table, technical-debt
- **Owner**: ratara5
- **Review date**: 2027-09-30, one year out rather than the 90 days used for live
  defects. This table is parked behind an unbuilt feature, so a 90-day review
  could only re-confirm that the feature is still unbuilt. Revisit when the
  feature is scheduled, not on a calendar.
- **Related**: TICKET-018 (the parent decision), TICKET-025, TICKET-027,
  TICKET-028, TICKET-029

## Description

`materials` is one of the five tables TICKET-018 decided to keep for future
features. It holds no ORM model, deliberately, and `app/models/reserved.py` keeps
Alembic's autogenerate from proposing to drop it.

Live structure, read on 2026-09-30 from `db_gestiket_acme`:

| Column | Type | Notes |
|---|---|---|
| `material_id` | `integer` | **primary key**, serial via `materials_material_id_seq` |
| `ticket_id` | `integer` | **no foreign key** — see below |
| `maintenance_id` | `uuid` | FK → `maintenances.maintenance_id`, `NO ACTION` |
| `spare_id` | `integer` | FK → `spares.spare_id`, `NO ACTION` |
| `material_description` | `text` | nullable |
| `qty` | `numeric` | **unscaled** — see below |
| `price` | `numeric` | **unscaled** — see below |

It holds **0 rows**.

## The two findings that matter more than the table

**1. `ticket_id` has no foreign key, and it is the wrong type for the obvious
target.** It is an `integer`, which would match `tickets.ticket_id` — also
`integer` — but no constraint is declared. So nothing stops a row pointing at a
ticket that does not exist. Meanwhile `maintenance_id` *is* constrained. The
table is half-anchored, which is a signature of a design that was abandoned
partway rather than one that was finished.

The same defect is present in `services.ticket_id` (TICKET-028). The two tables
are evidently a pair, so whichever feature is built will almost certainly settle
both together.

**2. `qty` and `price` are bare `numeric`, which for money is a trap.**
PostgreSQL's unconstrained `numeric` is exact arithmetic with unbounded scale,
and it is not the same as a fixed-scale money type. Both are also **nullable**,
so a row may carry a quantity and no price. TICKET-021 already found this exact
class of bug in the other reserved table, on `uom.factor_conversion`, which was
declared `numeric(5,2)` and could not represent `0.45359237` — a real constant,
truncated to `0.45`, silently corrupting every conversion. Whatever feature lands
here needs explicit scale on both columns, and needs to decide whether they are
nullable at all.

## Why no model was written

Per TICKET-018: a speculative model for an unbuilt feature is contradicted by the
real one, and a model in the codebase is far harder to remove than a table in a
script. Both of the findings above are exactly the kind of thing a real
specification would change — a model written today would encode `ticket_id` with
no constraint and `qty` with no scale, and would be the harder artefact to undo.

## What must be decided when the feature is built

1. Is `ticket_id` a real relationship? If so, add the foreign key. If the row
   belongs to a `maintenance` and not a `ticket` — which `maintenance_id`
   suggests — drop the column.
2. Is `materials` a line item like `services` (TICKET-028), in which case the two
   tables may be one table with a discriminator, or one table and one view.
3. Explicit scale and nullability on `qty` and `price`, with the TICKET-021
   lesson applied: check the constants that have to be stored, not the ones that
   happen to be stored today.
4. `spare_id` points at `spares`, which is a modelled table with 575 live rows.
   Decide whether a "material" is a `spare`, a *use* of a `spare` in a
   maintenance, or a third thing. The current shape allows both readings at once,
   which is why it is unsettled.

## Scope boundary

- No model. No migration. No change to the live database. No `DROP`.
- No `spare_id` "reset". TICKET-018 recorded a `to be reset` note against this
  column in `init.sql`; that comment is not present in the live database and
  `init.sql` has since been deleted, so the note no longer exists anywhere. It
  is recorded here instead, which is the durable form.

## Acceptance criteria

- [x] The table has a ticket of its own, satisfying TICKET-018's per-table
      requirement. This is that ticket; it records no code change.
- [x] The missing `ticket_id` foreign key and the unscaled, nullable money
      columns are recorded, so they are not rediscovered during the build.
- [ ] The feature is specified, and this ticket closes with it.
