# MIGRATION_PLAN — legacy seed removal

**Status: AWAITING APPROVAL.** Nothing below has been executed. The projection
install, the salvage and the removal all wait on approval of this plan.

- **Consumer branch**: `feature/agentic-bootstrap`
- **Base commit**: `01d098a` (tag `pre-agentic-layer`, moved to the branch tip)
- **Harness**: `v1.6.0`
- **Classifier**: `agentic --consumer . legacy` → **62 IDENTICAL, 27 SYMLINK, 6 UNKNOWN, 0 MODIFIED**

## Bundle selection

`.agentic.yaml` (already written):

```yaml
harness: 1.6.0
use: [core, backend, mobile, infrastructure, product]
targets: [claude, opencode, cursor, codex, gemini]
```

`[core, backend]` alone would **strand 11 of the seed's 18 skills** — the
infrastructure and product skills, which are `IDENTICAL` and would be deleted with
no projection to replace them. The selection is every bundle the seed covers:
`core` (7 skills), `backend` (backend-developer), `mobile`
(mobile-frontend-developer), `infrastructure` (6 skills + infrastructure-developer),
`product` (4 skills + product-strategy-analyst). `frontend` is empty and not
selected. `harness` is deliberately **not** selected — see gaps.

## Symlinks (27) — replaced in the projection commit, never deleted with their target

Sync refuses to write through these, so each is removed and the real file
projected in the **same commit**. No symlink target is deleted as part of this.

### Entrypoints → `docs/base-standards.md`

| Symlink | Target | Referrers to the target |
|---|---|---|
| `AGENTS.md` | `docs/base-standards.md` | the other three entrypoints; `docs/documentation-standards.md`; `HARNESS_ANALYSIS.md` |
| `CLAUDE.md` | `docs/base-standards.md` | as above |
| `GEMINI.md` | `docs/base-standards.md` | as above |
| `codex.md` | `docs/base-standards.md` | as above |

`docs/base-standards.md` is **CONSUMER-OWNED and must not be deleted** — four
documents still reference it. It is a hazard after migration; see below.

### `.opencode/agent/*.md` → `../../ai-specs/agents/*.md` (4)

`backend-developer.md`, `frontend-developer.md`, `infrastructure-developer.md`,
`product-strategy-analyst.md`. Referrers: only these links.

### `.opencode/skills/*` → `../../ai-specs/skills/*` (18)

Every seed skill, including `sync-agent-symlinks`, which has **no projection** —
see gaps. Referrers: only these links.

### README mirror (1)

`ai-specs/specboot-instructions.md` → `../README.md`. The link goes; the README
stays.

## UNKNOWN (6) — never deleted

### Tool-owned (3) — left byte-identical

`.opencode/.gitignore`, `.opencode/package.json`, `.opencode/package-lock.json`.
Not in the seed, so UNKNOWN, so untouched. This is the safety property working.

### Consumer content that merely lived under `ai-specs/` (3) — relocate, do not delete

| Path | Why it is not superseded | Proposed home |
|---|---|---|
| `ai-specs/harness-ia.md` | SPECIFIC: the consumer's old topology doc | `docs/` |
| `ai-specs/harness-assembler.md` | its content became the harness catalog; the file is consumer history | `docs/` |
| `ai-specs/scripts/code_review.sh` | SPECIFIC: depends on an unpinned external `agent` binary | `scripts/` |

These are excluded from the fingerprints on purpose, so the classifier calls them
UNKNOWN and the procedure cannot delete them. Relocation is a salvage step.

## IDENTICAL (62) — deletable after approval

| Group | Count |
|---|---|
| `ai-specs/agents/` | 4 |
| `ai-specs/skills/**` | 49 |
| `.opencode/commands/` (8 `opsx-*`, 1 `pipeline-preflight`) | 9 |
| `.opencode/skills/openspec-*/SKILL.md` | 8 |

`.opencode/workflows.txt` is **not** in the fingerprints: the harness stores the
workflow list in `manifest.yaml`, and the file is not a projected path. It is
UNKNOWN and stays unless you say otherwise.

## CONSUMER-OWNED — untouched

`docs/` and `openspec/`. Also untouched because they are outside the candidate
set: `HARNESS_ANALYSIS.md`, `.claude_example/`, `openspec_example/`, `app/`,
`tests/`, and everything else.

## Harness gaps and hazards

1. **`sync-agent-symlinks` has no projection.** The harness renamed it to
   `sync-agent-exposure` and placed it in the `harness` bundle, which a consumer
   does not select. Its subject — maintaining agent symlinks — is exactly what the
   harness forbids, so it is **obsolete**, not missing. Proposal: drop it. If you
   want it kept, `harness` must be selected, which also adds the
   `harness-developer` persona and the harness standard to this consumer.
2. **`docs/base-standards.md` becomes actively wrong.** Its §4 says "skills live
   in `ai-specs/skills`" and §5 instructs maintaining **relative symlinks** as the
   exposure path. After migration both are false and §5 contradicts the guard. It
   must be rewritten (or reduced to a pointer) in this PR. This is a consumer
   document edit, not a harness gap.
3. **`code_review.sh` is not provided by the projection.** Reported as a gap, not
   patched in the consumer; relocated in salvage.

## Proposed commits (each ends `Agentic-Layer: 1.6.0`)

1. **projection + lock** — remove the 27 symlinks, write `.agentic.yaml` and
   `.agentic.lock`, `agentic sync`. Symlink replacement and projection together.
2. **salvage** — relocate the 3 consumer files; rewrite `docs/base-standards.md`.
3. **seed removal** — delete the 62 IDENTICAL files and remove `ai-specs/` if
   empty.
4. **reference fixes** — repair any dangling references (Makefile, scripts, CI,
   README).

## Verify before delivery

`agentic sync --check` exits 0 · consumer tests pass · `git diff
pre-agentic-layer -- docs openspec` empty except approved salvage · no symlinks
outside `venv/`/`node_modules/` · UNKNOWN files byte-identical to the tag · a fresh
session finds commands and skills through the generated entrypoint.

## Rollback

`git reset --hard pre-agentic-layer` on this branch, or `git revert` commits 1–4.

---

**STOP.** Approve, amend, or reject: the bundle selection, the three relocations,
the `sync-agent-symlinks` drop, and the `docs/base-standards.md` rewrite.
