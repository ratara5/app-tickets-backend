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

## Resolution

Fixed. The reported failure reproduces, but it blames the wrong field.

### The crash is in `ext_by_type` first, not `allowed_types`

Sourcing the shipped `.env` aborts on `EXT_BY_TYPE`, because pydantic-settings
validates fields in declaration order and `ext_by_type` is declared first:

```
SettingsError: error parsing value for field "ext_by_type" from source "EnvSettingsSource"
```

`ALLOWED_TYPES` fails identically, just later. The ticket's captured traceback
names `allowed_types`, which sends you to the list when the mapping is the one
that actually stops the import. And a JSON *object* can never be shell-safe, so
making the list tolerant alone would not have fixed the reproduction.

### What changed

1. **Both** settings now accept a JSON form, a flat comma form, and the
   quote-stripped form a sourcing shell leaves behind.
2. `NoDecode` on both annotations. Without it pydantic-settings runs
   `json.loads` on the raw env string *before* any validator sees it, which is
   the crash; the tolerant parser was unreachable until this was added.
3. The shipped `.env.example` and `.env` carry the flat forms
   (`ALLOWED_TYPES=a,b,c`, `EXT_BY_TYPE=k:v,k:v`), so the documented
   `set -a; . ./.env` path produces the correct values rather than merely not
   crashing. Docker `env_file` and systemd `EnvironmentFile` read the file raw
   and are unaffected.
4. `tests/test_env_collection_settings.py` locks in every shape, plus the
   end-to-end shell-source comparison against a raw read.

### One thing worth recording

Tolerating the mangled form is a safety net, not a plan. A shell strips the
quotes but leaves the braces, so `{image/jpeg:.jpg,...}` parsed "successfully"
into a first key of `{image/jpeg` — a value that passes validation and is
quietly wrong, which is worse than the crash it replaced. The parser now strips
the punctuation, and a test asserts no key keeps a leading brace.

### Still true from the original notes

Option (b) remains the better long-term home for these values: they are policy,
not infrastructure secrets, and belong in a company-scoped config rather than
the process environment. This fix makes the current mechanism correct and
sourceable; it does not settle where the allow-list should ultimately live.
