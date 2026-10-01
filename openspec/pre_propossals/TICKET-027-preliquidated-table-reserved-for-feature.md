# `preliquidated` is reserved for a pre-liquidated feature that was never built

## Metadata

- **Summary**: the live table `preliquidated` has no ORM model and backs a
  pre-liquidated-dispensing feature that was designed and never built; it is
  kept, unmodelled, until that feature is actually specified
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
  TICKET-028, TICKET-029

## Description

`preliquidated` is one of the five tables TICKET-018 decided to keep for future
features. It holds no ORM model, deliberately, and `app/models/reserved.py` keeps
Alembic's autogenerate from proposing to drop it.

Live structure, read on 2026-09-30 from `db_gestiket_acme`:

| Column | Type | Notes |
|---|---|---|
| `ticket_id` | `integer` | **primary key**, and FK → `tickets.ticket_id`, `NO ACTION` |
| `timestamp_write_form` | `timestamp with time zone` | nullable |

It holds **0 rows**.

## What the shape says

This is a **marker table**, not a data table: one row per ticket, plus the moment
the form was written. The primary key *is* the foreign key, so it can record
"this ticket was pre-liquidated" and nothing more. There is no user, no operator,
no quantity, no reason, no audit trail.

Two things follow, and both are decisions rather than defects:

**1. "Pre-liquidated" is not defined anywhere.** The column name is a noun
adjective and nothing else describes it. The table name, the column name and the
foreign key do not say whether it means a chemical was decanted before the
maintenance ran, whether a form was pre-filled, or whether a ticket was
dispatched with work already assigned. Until that is written down, no migration
or model can be written correctly, because the column's meaning is the schema.

**2. A nullable timestamp on a marker table is ambiguous.** If
`timestamp_write_form` is `NULL`, that could mean the form was never written — or
that it was written at a time nobody recorded, or that the row was inserted
without it. Since the row's existence is the primary signal, the timestamp is
probably either always populated (and should be `NOT NULL`) or redundant (and
should go). It cannot be left optional without deciding which.

Also worth noting before the feature is written: this is the only one of the five
reserved tables whose primary key is a **real, enforced, modelled** foreign key
into a modelled table. `tickets` is a live model. So this table is the
structurally soundest of the five, and the one whose only problem is that its
meaning is undocumented.

## Why no model was written

Per TICKET-018: a speculative model for an unbuilt feature is contradicted by the
real one, and a model in the codebase is far harder to remove than a table in a
script. Here the risk is sharper than usual — a model would have to pick a meaning
for "pre-liquidated", and whichever meaning it picked would become the one the rest
of the codebase uses, by accident.

## What must be decided when the feature is built

1. Define "pre-liquidated". Nothing else can be decided first.
2. Is one row per ticket enough, or does the feature need many rows per ticket
   (a log of dispensings)? If it needs a log, the primary key must change and the
   current one-row-per-ticket shape is wrong, not merely minimal.
3. `timestamp_write_form`: `NOT NULL`, or removed as redundant.
4. Is the state reversible? There is no `undone` column and no soft delete, so
   un-pre-liquidating a ticket means `DELETE`. For an auditable process that is
   probably wrong, and this is the point at which it should be decided.

## Scope boundary

- No model. No migration. No change to the live database. No `DROP`.

## Acceptance criteria

- [x] The table has a ticket of its own, satisfying TICKET-018's per-table
      requirement. This is that ticket; it records no code change.
- [x] The open semantic question is recorded explicitly, so the build starts from
      a definition rather than from a guess about the column name.
- [ ] The feature is specified, and this ticket closes with it.
