# `hollidays` is reserved for a holiday-calendar feature that was never built

## Metadata

- **Summary**: the live table `hollidays` has no ORM model and backs a calendar
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
- **Related**: TICKET-018 (the parent decision), TICKET-026, TICKET-027,
  TICKET-028, TICKET-029

## Description

`hollidays` is one of the five tables TICKET-018 decided to keep for future
features. It holds no ORM model, deliberately, and `app/models/reserved.py` keeps
Alembic's autogenerate from proposing to drop it.

Live structure, read on 2026-09-30 from `db_gestiket_acme`:

| Column | Type | Notes |
|---|---|---|
| `holliday_date` | `date` | **primary key** — one row per day, so a day cannot have two titles |
| `title` | `text` | nullable |

It holds **0 rows** and nothing references it.

## The finding that matters more than the table

**The application already has holiday support, and it does not use this table.**
`get_holidays` in `app/core/utils/dates.py:44` resolves holidays from the
`holidays` **Python package**:

```python
def _holidays(country: str, year: int) -> holidays.HolidayBase:
    return holidays.country_holidays(country, years=[year - 1, year])
```

So the table is not merely unimplemented — it duplicates capability the service
already has, and does it less completely. The `holidays` package ships per-country
calendars, movable holidays and observed days; this table has a single `title`
column keyed by date, so it can express neither per-country variation nor a
holiday that is observed on a different day than it falls.

The likely honest outcome when this feature is written is that the table is
**dropped**, not modelled. That is recorded here as the expectation, not as a
decision — nothing is dropped while no feature exists to justify the change.

## Why no model was written

Per TICKET-018, and repeated so it is not "helpfully" undone: a speculative model
for an unbuilt feature is contradicted by the real one, and a model in the
codebase is far harder to remove than a table in a script. The spec would be
written twice and the wrong one would win.

## The name trap

The table is **`hollidays`, with a double L**, in both `init.sql` and the live
database. It is not `holidays`. Any query, ticket or rename that assumes the
correct spelling will silently not find it, because `holidays` is a valid
identifier in the same schema.

`app/models/reserved.py` must keep the double L. Correcting the spelling to
`holidays` would make autogenerate stop protecting the real table, because the
exclusion list would name something that does not exist. The rename, when it
happens, has to change all of: the live database, a migration, `deploy/schema.sql`
by regeneration, `app/models/reserved.py`, and TICKET-018 — in one change.

## What must be decided when the feature is built

1. **Does this table need to exist at all**, given the `holidays` package already
   provides the capability? Dropping it is the default expectation.
2. If it is kept: the single-`title` shape cannot represent per-country
   calendars, so `holiday_date` as primary key is almost certainly wrong. It
   needs a country column, and then the key is wrong too.
3. If it is dropped: `0` rows means no data migration, and nothing references
   it, so the drop is clean. The typo'd name is then a non-issue.

## Scope boundary

- No model. No migration. No change to the live database. No `DROP`.
- Deliberately **not** done, and tracked in TICKET-018's acceptance criteria
  rather than here, because it is a cross-cutting change: the `hollidays` →
  `holidays` rename.

## Acceptance criteria

- [x] The table has a ticket of its own, satisfying TICKET-018's per-table
      requirement. This is that ticket; it records no code change.
- [x] The finding that the `holidays` Python package already covers this
      capability is recorded, so whoever builds the feature does not write it
      twice.
- [ ] The feature is specified, and this ticket closes with it.
