# Harness adoption — app-tickets-backend

Consumer: `/home/ratara5/Documents/python_scripts/app-tickets-backend`
Harness: `/home/ratara5/Documents/python_scripts/agentic-layer` (v1.14.0)
Canonical procedure: `docs/ADOPTION.md` in the harness checkout.
Operation history: `docs/OPERATION-HISTORY.md` in the harness checkout, governed by
`docs/adr/0006-operation-history.md` (ADR-0006).

## What this run is

The consumer is already `ADOPTED` at harness **1.6.1**; the migration was merged in
`f18248e`. It is not a `PRE_HARNESS` consumer, so the first-adoption phases do not
repeat. What remains is the path the canonical procedure prescribes for an
`ADOPTED` consumer: re-detect, skip the learn gate because the seed is gone,
install the new projection, and delete nothing.

| Phase | This run |
|---|---|
| survey | re-detect and record the state below |
| learn gate | skipped: `ai-specs/` was removed in `a258a7a`; no pre-harness material remains |
| install | bump the pin to `1.14.0`, sync, check |
| remove | skipped: no unprojected legacy candidates; the tag remains the evidence |

Delivery is not complete until the operation is recorded (step 8). ADR-0006 keeps
that write on the harness side: this consumer session never writes the harness
repository, and the row is appended by the operator or the harness-side session
that consumes `HARVEST_REQUEST.md`.

## Detected state

| Fact | Value |
|---|---|
| State | `ADOPTED` (harness 1.6.1) |
| Branch | `main` |
| HEAD | `f18248e` |
| `pre-agentic-layer` tag | `01d098a`, an ancestor of `HEAD` |
| Working tree | dirty: 9 paths from the `local-stack` work (listed below) |
| Order form | `.agentic.yaml` pins `harness: 1.6.1`, 5 bundles, 5 targets |
| Lock | `.agentic.lock`, 322 files, 0 pointers |
| Projection evidence | 5 target directories plus 4 root entrypoints; no symlinks among the locked outputs |
| `sync --check` at 1.6.1 | exit 0: `no drift. 322 files match harness 1.6.1.` |
| `sync --check` at 1.14.0 | exit 2: pin 1.6.1 vs checkout 1.14.0 — a version disagreement, not drift |
| Legacy candidates | none; `ai-specs/` is absent |
| Remaining `UNKNOWN` paths | `.opencode/workflows.txt` (consumer-owned) and the tool-owned `.opencode/.gitignore`, `package.json`, `package-lock.json`, `node_modules/` |
| Selected source | local checkout at `a3c9a48`; its `manifest.yaml` declares 1.14.0 |
| Release tag | **missing**: no `v1.14.0` locally, and `origin` publishes only `v1.6.0` and `v1.6.1` |

Under the state precedence in `docs/ADOPTION.md`, a valid lock whose recorded
outputs all match and no unprojected legacy candidates is `ADOPTED`. The
`sync --check` failure against 1.14.0 is a source/pin disagreement: the checkout
declares a newer version than the consumer pins. It is not drift in the
projection.

The last row is the only blocker outside the consumer. The CI workflow fetches
`v<version>` from `HARNESS_REPO`, so the upgrade cannot go green until the harness
publishes `v1.14.0`.

## Before step 1

The tag and the snapshot must name the same commit. The tag already exists and is
the durable evidence, so do not create or move it; verify it instead.

```sh
cd /home/ratara5/Documents/python_scripts/app-tickets-backend
git status --short
```

Expected:

```text
 M Dockerfile
 M README.md
 M docs/deployment-guide.md
 M infra/local/docker-compose.yml
 D infra/provision/README.md
 M infra/vps/docker-compose.yml
 M openspec/changes/local-stack/tasks.md
 M tests/test_local_assets.py
 M tests/test_provisioning.py
?? docs/runbooks/ADOPTION_STEPS.md
```

Choose one:

- **Commit the `local-stack` work first (recommended).** It keeps the upgrade
  commit purely generated output and makes the review diff unambiguous.
- **Stash it and restore after the upgrade.** Do not stash this guide with it; the
  guide belongs to the upgrade record.

None of those 9 paths is projected, so the file counts in step 4 are the same
either way. If you keep the tree dirty, take a safety copy first:

```sh
cp -a /home/ratara5/Documents/python_scripts/app-tickets-backend \
  /tmp/app-tickets-backend-safety-$(date +%Y%m%d-%H%M%S)
```

Confirm the tag before touching anything:

```sh
git rev-parse pre-agentic-layer
git merge-base --is-ancestor pre-agentic-layer HEAD && echo "ancestor"
```

Expected: `01d098a69361a75143f015650454d3af582bb7b4` and `ancestor`.

## Step 1 — Survey (read-only)

Re-detect the state and prove the old projection is intact. This writes nothing.

```sh
cd /home/ratara5/Documents/python_scripts/app-tickets-backend
git rev-parse HEAD
git ls-files | grep -c '^ai-specs/' || true
```

Expected: `f18248e...`, and `0` for the seed count.

Extract the old harness version and check the lock against it:

```sh
rm -rf /tmp/harness-1.6.1
mkdir -p /tmp/harness-1.6.1
cd /home/ratara5/Documents/python_scripts/agentic-layer
git archive v1.6.1 | tar -x -C /tmp/harness-1.6.1
cd /home/ratara5/Documents/python_scripts/app-tickets-backend
/tmp/harness-1.6.1/bin/agentic sync --check
```

Expected: `agentic: no drift. 322 files match harness 1.6.1.`

Record the pre-upgrade failure against the current checkout:

```sh
cd /home/ratara5/Documents/python_scripts/agentic-layer
./bin/agentic sync --check --consumer \
  /home/ratara5/Documents/python_scripts/app-tickets-backend
```

Expected, exit 2:

```text
agentic: .agentic.yaml pins harness 1.6.1 but this checkout is 1.14.0.
  Fetch it:  git fetch --tags && git checkout 1.14.0
  Or change the pin in .agentic.yaml and sync again.
```

The suggested `git checkout 1.14.0` does not work yet: no such tag exists. That is
step 2.

## Step 2 — Publish the release tag (harness-side prerequisite)

The consumer's CI reads `harness:` from `.agentic.yaml`, clones
`v<that version>` from `HARNESS_REPO`, and runs `sync --check --from v<version>`.
A local checkout is enough for the operator, but not for CI.

Have the harness maintainer tag the commit whose `manifest.yaml` declares 1.14.0
(currently `a3c9a48`) and push it:

```sh
cd /home/ratara5/Documents/python_scripts/agentic-layer
grep -m1 '^version:' manifest.yaml
git tag v1.14.0 a3c9a48          # only if the tag is absent; never move one
git push origin v1.14.0
git ls-remote --tags origin refs/tags/v1.14.0
```

Expected: `version: 1.14.0`, then one line naming
`refs/tags/v1.14.0`.

Stop and fix if:

- the tag already exists at another commit — do not move or delete it; release a
  new version instead;
- the push is rejected or the remote still lists only `v1.6.0` and `v1.6.1` —
  stop before the pin bump. The consumer can sync locally, but CI will fail on a
  tag that does not exist.

This is a harness release action, not a consumer edit. Do not work around it by
pointing CI at a branch; a branch makes two consumers pinning the same version
receive different bytes, which is why the workflow reads a tag.

## Step 3 — Bump the pin

Edit `.agentic.yaml` at the consumer root. Change one line; leave the bundles and
targets alone.

```yaml
# before
harness: 1.6.1

# after
harness: 1.14.0
```

```yaml
harness: 1.14.0
use: [core, backend, mobile, infrastructure, product]
targets: [claude, opencode, cursor, codex, gemini]
```

`entrypoints` defaults to `generated`, which is what the tree already contains, so
no key is needed. The selected bundles still exist in 1.14.0. `frontend` is now a
separate bundle, but `mobile` already carries the host-agnostic frontend core plus
the mobile delta; `documents` targets Apps Script hosts and does not apply here;
`harness` is provider-only.

## Step 4 — Sync

Run sync from the harness checkout, not from inside the consumer:

```sh
cd /home/ratara5/Documents/python_scripts/agentic-layer
./bin/agentic --consumer \
  /home/ratara5/Documents/python_scripts/app-tickets-backend sync
```

Expected:

```text
agentic: synced harness 1.14.0 into /home/ratara5/Documents/python_scripts/app-tickets-backend
  bundles  core, backend, mobile, infrastructure, product
  targets  claude, codex, cursor, gemini, opencode
  openspec 1.4.1 (pinned)
  files    352 written, 0 pointers written, 0 stale removed
```

The counts were measured on a scratch copy of `HEAD` synced at 1.14.0. The dirty
paths listed above are not projected, so the real run produces the same numbers.
If `stale removed` is non-zero, stop and inspect: at this pin it must be zero.

Then check:

```sh
./bin/agentic sync --check --consumer \
  /home/ratara5/Documents/python_scripts/app-tickets-backend
```

Expected: exit 0.

```text
agentic: no drift. 352 files and 0 pointers match harness 1.14.0.
```

## Step 5 — Review the diff

The upgrade is additive: 30 new files, 352 rewritten locked files, none deleted.
The 30 are six artifacts repeated in each of the five targets:

| Artifact | Bundle | Why it appears |
|---|---|---|
| `skills/adopting-the-harness/` | core | the skill for this procedure |
| `skills/openspec-task-mandatory-steps/` | core | the task procedure |
| `standards/documentation/` | core | documentation standard |
| `agents/frontend-developer.md` | mobile | host-agnostic frontend planner |
| `agents/mobile-frontend-implementer.md` | mobile | mobile implementation role |
| `standards/frontend.md` | mobile | host-agnostic frontend invariants |

Per-target file counts in the new lock:

| Target | Files |
|---|---|
| `.claude/` | 71 |
| `.opencode/` | 71 |
| `.cursor/` | 72 |
| `.codex/` | 63 |
| `.gemini/` | 71 |
| root entrypoints | 4 |
| **total** | **352** |

`.opencode/` holds one more file than the lock counts: `workflows.txt` is
consumer-owned and is not written by sync.

Confirm the ownership boundary:

```sh
cd /home/ratara5/Documents/python_scripts/app-tickets-backend
git status --short
git diff --stat -- .agentic.yaml .agentic.lock
```

Expected: the status adds only `.agentic.yaml`, `.agentic.lock`, the five target
directories, the four root entrypoints, and this guide. The 9 pre-existing paths
must look exactly as they did before step 4. `docs/`, `openspec/`, and application
code are untouched.

Confirm the new skill is in the selected target:

```text
.opencode/skills/adopting-the-harness/SKILL.md
```

Do not hand-edit anything under `.claude/`, `.opencode/`, `.cursor/`, `.codex/`,
`.gemini/`, or the root entrypoints. Generated output is repaired by sync, not by
editing the target directory.

## Step 6 — Commit

Commit the pin, the projection, and the lock as one commit, separate from the
`local-stack` work:

```sh
git add .agentic.yaml .agentic.lock \
  AGENTS.md CLAUDE.md codex.md GEMINI.md \
  .claude .opencode .cursor .codex .gemini
git commit -m "Upgrade the agent harness projection to agentic-layer v1.14.0" \
  -m "Agentic-Layer: 1.14.0"
```

`.opencode/.gitignore` keeps `node_modules/`, `package.json`, and
`package-lock.json` out of the commit. Do not stage the 9 `local-stack` paths or
this guide into the projection commit.

## Step 7 — Verify and hand off

Local gates:

```sh
cd /home/ratara5/Documents/python_scripts/app-tickets-backend
make harness HARNESS=/home/ratara5/Documents/python_scripts/agentic-layer
make gate
```

Expected: `no drift. 352 files and 0 pointers match harness 1.14.0.`, then the
consumer's contracts and unit suite pass.

`make harness` could not pass at 1.6.1: the target already calls
`$(HARNESS)/bin/agentic --consumer . sync --check`, and the 1.6.1 CLI has no
`--consumer` flag. The upgrade also repairs that target.

CI: `.github/workflows/agentic-check.yml` reads the pin and clones
`v1.14.0` from `HARNESS_REPO`. It passes only after step 2's tag is published.
Open a fresh agent session and confirm the generated entrypoint exposes the new
skills and commands before merging.

## Step 8 — Hand off the operation-history row

ADR-0006 makes recording part of delivery. The register is
`docs/OPERATION-HISTORY.md` in the harness checkout. This consumer session never
writes the harness repository, so the operator — or the harness-side session that
consumes `HARVEST_REQUEST.md` — appends the row. This run produced no harvest
request (the learn gate was skipped), so the operator appends it.

The register has three types and no `upgrade` type. Record this run as an
`adoption`: a consumer's projection was brought onto a new harness version. It is
not a `harvest` (no snapshot, no candidates) and not an `inventory` (material was
not merely identified). Put the upgrade commit from step 6 in the Consumer cell;
the Baseline cell stays the old adopted version.

The Record cell names `consumer:MIGRATION_PLAN.md`, which is the consumer-side
record the canonical report points at. Add a dated "Upgrade to 1.14.0" section to
that file — with the survey, install and check evidence above — so the reference
resolves. Its existing 1.6.0 header is historical; add a section, do not rewrite
the old record.

Hand over these fields:

| Field | Value |
|---|---|
| Date | the date the row is appended |
| Type | `adoption` |
| Consumer | `app-tickets-backend@<upgrade-commit>` |
| Baseline | `ADOPTED at v1.6.1 (322-file lock)` |
| Harness | `v1.14.0 at a3c9a48` (or the tagged release commit) |
| Outcome | `upgraded the projection from v1.6.1 to v1.14.0; 30 files added, 0 deleted; sync --check 0` |
| Record | `consumer:MIGRATION_PLAN.md` |
| Provenance | `live` |

Expected: one new row in the harness register; the consumer's `MIGRATION_PLAN.md`
gains the referenced section; nothing else changes. The register names the
consumer and points at the record, and quotes nothing. Do not put candidate text,
a diff, a consumer-internal path beyond the single record reference, a secret, or
a business term in the row: the file is exempt from the leak scan only on that
condition, and `tests/test_operation_history.py` checks the table shape, the
provenance vocabulary, and the report/link coverage.

Retention is append-only and there is no automation yet. A later upgrade adds a
new row and leaves this one in place; a correction is an appended note, never a
silent rewrite. ADR-0006 deliberately keeps the register hand-written — no CLI,
no JSON, no generated file — so do not add automation in this change.

Stop and fix if:

- someone proposes writing the row from the consumer session — that boundary is
  the point of ADR-0006 and `ADOPTION.md`;
- the referenced `MIGRATION_PLAN.md` section does not exist — add it before the
  row is appended, or the register points at nothing;
- the row needs a fact the delivery report does not carry — use `unknown` rather
  than inferring it, and say so in the report.

Two facts a reader of the register should not misread:

- the 2026-10-03 `harvest (origin)` row for `app-tickets-backend@01d098a` is the
  pre-migration extraction, not the 1.6.1 adoption;
- the backfill closed on 2026-11-18, so no `backfilled` adoption row exists for
  this consumer. Absence is not evidence that the adoption did not happen; this
  upgrade adds a `live` row and does not rewrite the backfill.

## Rollback

In order of preference:

1. `git revert <upgrade-commit>` — the pin, projection, and lock revert together,
   and the removal commit from the original migration is untouched;
2. restore the old projection from the tag if a partial tree is needed:
   `git checkout pre-agentic-layer -- <paths>`, then sync with the 1.6.1 checkout;
3. restore the safety copy from this guide's "Before step 1".

The `/tmp` probe and the `harness-1.6.1` extraction are scratch inputs, not
rollback sources. The `pre-agentic-layer` tag is the durable evidence; do not move
or delete it during a rollback.

## Expected delivery report

```text
State: ADOPTED (1.6.1) -> ADOPTED (1.14.0)
Harness source: /home/ratara5/Documents/python_scripts/agentic-layer @ a3c9a48 (v1.14.0)
Phases:
  survey        done (state re-detected, 322-file lock verified at 1.6.1)
  learn gate    skipped (ai-specs/ removed in a258a7a; no seed)
  install       done (352 files, 0 pointers, sync --check 0)
  remove        skipped (no unprojected legacy candidates)
Approvals: upgrade plan + safety copy
Snapshot: not requested (no seed)
Release: v1.14.0 published to origin (required for CI)
Register: adoption; app-tickets-backend@<upgrade-commit>; baseline ADOPTED at v1.6.1;
  v1.14.0 at a3c9a48; upgraded (30 added, 0 deleted, sync --check 0);
  consumer:MIGRATION_PLAN.md; live
Rollback: git revert <upgrade-commit>
```

## Questions and answers recorded during the upgrade

### 1. Why is this not a `PRE_HARNESS` adoption?

Because the evidence says otherwise. `.agentic.yaml` and `.agentic.lock` exist,
the lock's 322 recorded outputs all match harness 1.6.1, and `ai-specs/` is gone.
`PRE_HARNESS` requires no order form or lock and candidate paths on disk. This
consumer has the opposite: a valid projection and no seed.

### 2. Why does `sync --check` exit 2 before the upgrade if the lock is valid?

The lock is valid, but the checkout is 1.14.0 while the consumer pins 1.6.1. The
CLI refuses to compare a projection against a harness version the consumer did not
pin and prints both sides. That is a source/pin disagreement, not drift. After
step 3 the same command returns `no drift`.

### 3. Why rewrite 352 files when only 30 are new?

Sync derives the complete projection from the catalog. A harness version can
change any rendered byte: shared standards, agent front matter, command bodies,
and the entrypoints all carry versioned text. The 30 new paths are only the files
that did not exist before; the rewrite is what keeps the lock's hashes honest.
Review it as generated output, not as hand edits.

### 4. Why does the lock count 352 files when the directories hold 353?

`.opencode/workflows.txt` is consumer-owned. The harness pins the workflow list in
`manifest.yaml` and does not write the file; a consumer test depends on it. It is
classified `UNKNOWN`, not projected, so it stays and is not counted in the lock.

### 5. Why is the learn gate skipped rather than answered?

There is nothing left to harvest. The seed was removed in `a258a7a`, and the
`pre-agentic-layer` tag at `01d098a` still provides the historical evidence. A
gate over an empty seed is recorded as skipped with that evidence, never reported
as accepted or declined.

### 6. Do I need to add `frontend`, `documents`, or `harness` to `use`?

No. `mobile` now carries `frontend-developer`, the mobile implementer, the
host-agnostic `frontend` standard, and `mobile-frontend`. `documents` is for
Apps Script-style hosts (the CRMSUra case), not this backend. `harness` exists for
the provider's own checkout; selecting it in a consumer would project the
maintainer's artifacts.

### 7. Why can local sync succeed while CI fails?

Local sync reads the operator's checkout. CI is not allowed to trust a working
tree: it clones `v<version>` from `HARNESS_REPO`, so the tag must exist there.
This is why step 2 precedes the pin bump. The same rule is why the workflow reads
the version from `.agentic.yaml` instead of duplicating it.

### 8. Is `docs/runbooks/ADOPTION_STEPS.md` projected or overwritten by sync?

No. `docs/` is consumer-owned. `agentic sync` and the legacy removal procedure
never write or delete it, so this runbook survives future upgrades and can be
revised in place.

### 9. Is the `/tmp` copy of the old harness a rollback source?

No. It is an extraction of tag `v1.6.1` used to prove the old lock, and the scratch
probe is a copy of `HEAD` with no Git history. Reversibility comes from Git: the
upgrade commit is a clean revert, and `pre-agentic-layer` names the pre-migration
tree.

### 10. Does this upgrade have to write the operation history itself?

No. ADR-0006 and `ADOPTION.md` keep the register's writer on the harness side. The
consumer-side delivery report carries the field values; the operator, or the
harness-side session that consumes `HARVEST_REQUEST.md`, appends the row. This run
has no harvest request, so the operator appends it. Writing
`docs/OPERATION-HISTORY.md` from the consumer session would cross the boundary the
adoption procedure exists to preserve.

### 11. Which register type does an upgrade use?

`adoption`. The register has three types and no `upgrade` type: an upgrade brings a
consumer's projection onto a new harness version, while `harvest` requires a
prepared snapshot and candidates and `inventory` means material was identified but
not harvested. Both of those would misreport this run. If a future ADR adds an
`upgrade` type, the schema and the existing rows must be updated in the same
change, per ADR-0006 decision 4.

### 12. Is the existing `app-tickets-backend@01d098a` row this adoption?

No. That row is the 2026-10-03 `harvest (origin)` extraction from the live tree,
before the consumer had a harness pin. The 1.6.1 adoption left its record in the
consumer (`MIGRATION_PLAN.md`), and the backfill closed on 2026-11-18 without an
adoption row for this consumer. Absence is not evidence that it did not happen.
The upgrade adds a `live` adoption row; it does not rewrite the backfill.
