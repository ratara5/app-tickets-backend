# Bug: PRESIGNED_TTL is documented as seconds, consumed as hours, and the value differs from the default

## Metadata

- **Summary**: One variable with three meanings — the settings default, the template value, and the call site all disagree
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: backend, configuration

## Description

| Source | Value | Unit |
|---|---|---|
| `app/core/settings.py:47` | `3600` (`# 1 hour`) | implied seconds |
| `.env.example:69` | `1` | hours |
| `app/services/maintenance_service.py:322` | `expires_hours=settings.presigned_ttl` | hours |

The name carries no unit, the docstring and the default disagree with the template, and the
only consumer multiplies the value into `timedelta(hours=...)`.

**Impact:** any new code that reads `presigned_ttl` as seconds (the natural reading of the name
and of the default) produces **1-second** URLs when the shipped `.env` is used, or a
**3600-hour** lifetime when the variable is absent. Both fail in production and neither fails
in a smoke test that only checks that a URL was returned.

## Reproduction

```bash
grep -n presigned_ttl .env.example app/core/settings.py
grep -rn "presigned_ttl" app/ | grep -v settings.py
```

## Notes

- Fix by making the unit explicit: rename to `PRESIGNED_TTL_MINUTES` (or seconds), set the
  default and the template to the same value, and pass a `timedelta` at the call site so the
  unit is visible in the code.
- Media URLs are signed with this value, so a change invalidates nothing already delivered
  (each URL is signed with its own expiry) but must be consistent across the API and the
  mobile client expectations.
