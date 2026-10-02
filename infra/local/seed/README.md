# Local seed data

Synthetic reference rows for `make setup-local`. Everything here is invented.

## Nothing in this folder came from a production database

`infra/schema.sql` is `--schema-only` and contains no `INSERT`, so no production
row exists anywhere in this repository to copy. These rows were written by hand.
They are recognisable as synthetic on sight: names are `Local …`, identifiers are
`EQ-LOCAL-0001`, and the seed account uses a fixed reserved id rather than a real
one. `tests/test_local_assets.py::test_seed_rows_are_not_production_shaped` is the
guard that keeps it that way.

## Why this folder is `seed/` and not `data/`

`.gitignore:6-7` excludes `**/data/*` except `.gitkeep`, so a committed CSV under
`infra/local/data/` would be invisible to git and silently absent from a fresh
clone — `make setup-local` would then load nothing and report success. The
committed rows therefore live here, and `setup.sh` copies them into
`infra/local/data/` (git-ignored) before loading. Decided in `tasks.md` §8.1.

## `fsm_users.csv` is deliberately NOT here

It is generated at bring-up from `SEED_USER_PASSWORD` in the developer's
git-ignored `.env`, via `etl/get_hash.py`. Committing it would mean committing
either a password or a fixed hash, and a fixed hash gives every developer the same
password and a salted hash that cannot be regenerated. `get_hash.py` re-salts on
every run, which is why the hash is produced at setup time rather than stored.

## Tables not in this folder, and why

- **`labsdls.csv` is absent.** `labsdls` appears nowhere in `etl/seed_db.sh` — not
  in `REFERENCE_TABLES`, not in `BUSINESS_TABLES`. The loader's allowlist is its
  security boundary, so a `labsdls.csv` would be skipped with "not on the
  allowlist" on every run. A committed file that provably does nothing is worse
  than an absent one. Recorded in `tasks.md` §8.1.
- **`materials`, `services`, `preliquidated` are absent.** They are business data:
  `materials.maintenance_id` and `services.maintenance_id` reference
  `maintenances`, and `preliquidated.ticket_id` is NOT NULL and references
  `tickets`. Loading them needs maintenance and ticket rows, which are the
  operational record rather than reference data. Recorded as §8.17.

## Column order is not free

`seed_db.sh` loads each CSV with `COPY … (columns)` in the order given in
`SELF_REF_LOADS` for `uom`, and from the table's own column list otherwise. The
header row in each file is what it matches, so a reordered column is a load error
rather than a silent mis-assignment. `uom` must load parent-before-child: a row
whose `ref_unit` names a unit absent from the file is refused, because
`ref_unit` is a self-reference and an unresolvable one is a cycle.
