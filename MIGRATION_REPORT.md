# Migration report — legacy seed removal

Consumer: `app-tickets-backend`. Harness: `v1.6.1`. Base: `pre-agentic-layer`
(`01d098a`). Branch: `feature/agentic-bootstrap`.

The consumer was migrated from the hand-maintained `ai-specs/` symlink seed to the
harness projection. Four commits, each ending `Agentic-Layer: 1.6.1`:

1. `2a438c3` projection + lock (symlink replacement)
2. `dde1a38` salvage
3. `a258a7a` seed removal
4. `f991dfb` reference fixes

## Deleted

- 44 files under `ai-specs/` — the canonical copies of the agents and skills the
  harness now projects. Every one classified `IDENTICAL` against the recorded
  fingerprints, so none had diverged.
- `ai-specs/specboot-instructions.md`, the symlink to the README. The link went;
  the README stayed.
- The `ai-specs/` tree itself.

## Salvaged

Three files under `ai-specs/` were **not** harness material and were excluded from
the fingerprints so the procedure could not delete them:

| File | New home | Why |
|---|---|---|
| `ai-specs/harness-ia.md` | `docs/harness-ia.md` | the consumer's old topology map (historical) |
| `ai-specs/harness-assembler.md` | `docs/harness-assembler.md` | its content became the harness catalog (historical) |
| `ai-specs/scripts/code_review.sh` | `scripts/code_review.sh` | depends on an unpinned external binary |

`docs/base-standards.md` was rewritten. It was the target of all four entrypoint
symlinks and stated two things that became false: that skills live in
`ai-specs/skills`, and that artifacts are exposed with relative symlinks — the
second contradicts the harness, which refuses to write through a symlink.

## UNKNOWN — left untouched

- Tool-owned: `.opencode/.gitignore`, `.opencode/package.json`,
  `.opencode/package-lock.json`.
- Consumer-owned: `.opencode/workflows.txt` — the harness pins the workflow list in
  `manifest.yaml` and does not write it; a consumer test depends on it.

## Harness gaps and findings

1. **`sync-agent-symlinks` has no projection.** The harness renamed it to
   `sync-agent-exposure` and put it in the `harness` bundle, which a consumer does
   not select. Its subject — maintaining agent symlinks — is what the harness
   forbids, so it was **dropped as obsolete**, not replaced.
2. **Two classifier defects, fixed in the harness before this migration
   finished.** `superseded` was recorded but not honoured, so a path the harness
   also projects was reported `IDENTICAL` (deletable); and a seed symlink path that
   became a projected directory raised `IsADirectoryError`. Both now report
   `PROJECTED`. Harness commits `ce27910` and `73ca57d`.
3. **`{{CONSUMER_DOCS}}` rendered an absolute path into the committed entrypoint.**
   Found by running this consumer's CI for real: the job regenerated the
   entrypoint under its own path, so `sync --check` reported drift no local run
   could reproduce. **Fixed in harness 1.6.1** — the renderer now emits the
   relative `docs`, with a regression test. This is why the consumer pins 1.6.1
   rather than 1.6.0.
6. **The CI template installed OpenSpec but not PyYAML**, so the check died on
   `agentic: PyYAML is required` after cloning correctly. **Fixed in 1.6.1.**
4. **`openspec/config.yaml` still declares `ai_specs_structure`** for the removed
   tree. Left untouched: `sync` never writes `openspec/`, and the migration's own
   verification requires it byte-identical to the base.
5. **`packages/specboot/` still ships a template that generates the old symlink
   layout.** Consumer-owned, out of scope.

## Verification

| Check | Result |
|---|---|
| `agentic sync --check` | exits 0 — 322 files match `v1.6.1` |
| Consumer tests | 426 passed; 4 failed |
| The 4 failures | `tests/test_worksheets.py` PDF tests — **pre-existing**, confirmed failing at `pre-agentic-layer` |
| `git diff pre-agentic-layer -- openspec` | empty |
| Symlinks in the committed tree | none |
| `ai-specs/` | gone |

## Rollback

```sh
git reset --hard pre-agentic-layer    # discard the whole migration on this branch
```

or revert commits 1–4 individually. The tag and a bundle backup exist in the
consumer.

## Before this PR can merge

The harness must be pushed with its tag: the consumer CI workflow
`.github/workflows/agentic-check.yml` fetches `v1.6.1` from the published
repository and runs `agentic sync --check`. Until the tag is on `origin`, that job
cannot resolve the pin.
