# Improvement: ALLOWED_TYPES as a JSON list makes `.env` unsafe to source from a shell

## Metadata

- **Summary**: `set -a; . .env` strips the quotes inside the JSON array and the app aborts at import
- **Issue Type**: Improvement
- **Project**: app-tickets-backend
- **Priority**: Low
- **Labels**: backend, configuration, developer-experience

## Description

`app/core/settings.py` declares `allowed_types: list[str]` and `.env.example` carries
`ALLOWED_TYPES=["image/jpeg","image/png",...]`. Docker's `env_file` and systemd's
`EnvironmentFile` both read the file raw, so those consumers are fine.

Any **shell** consumer is not. `set -a; . ./.env` performs quote removal, so the application
receives `[image/jpeg,image/png,...]`, which is not valid JSON, and pydantic aborts the process
at import:

```
pydantic_settings.exceptions.SettingsError: error parsing value for field "allowed_types"
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes
```

**Impact:** any script, Makefile, or documented command that sources `.env` breaks the app in a
way whose error message points at an unrelated field. This was hit while writing the
deployment scripts.

## Reproduction

```bash
set -a; . ./.env; set +a
python -c "import app.core.settings"   # SettingsError
```

## Notes

- Options: (a) accept a comma-separated list and parse it with a field validator, keeping the
  JSON form working for compatibility; (b) move the allow-list into the database or a
  company-scoped config file where it belongs, since it is a policy value rather than an
  infrastructure secret.
- Independent of the fix, shell consumers must read single keys (`sed -n 's/^KEY=//p' .env`)
  instead of sourcing the file. The deployment skill documents this.
