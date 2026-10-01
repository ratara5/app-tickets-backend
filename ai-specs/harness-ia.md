# Harness IA

The map of this agent harness: what is canonical, what is a pointer, and what an
agent is expected to read in what order. This document exists so the harness can be
extended without inventing a second copy of something.

`ai-specs/` is the canonical home for agent-facing artifacts. Everything under an
agent-specific folder (`.opencode/`, `.claude_example/`) is either a symlink into
`ai-specs/` or a vendor directory from an external tool. It is never authored by
hand. See `docs/base-standards.md` §5 for the symlink integrity rule this enforces.

## 1. Read order

An agent working in this repository is expected to load, in this order:

1. `README.md` — the entry point, reached as the standards and the specboot
   instructions (see §3). Gives the stack, the setup, and the API surface.
2. `docs/base-standards.md` — universal rules. Reached as `AGENTS.md`,
   `CLAUDE.md`, `GEMINI.md`, `codex.md` (see §3).
3. `openspec/config.yaml` — the machine-readable context and standards block:
   tech stack, the `ai_specs_structure` tree, mandatory implementation steps.
4. The relevant `ai-specs/skills/<skill>/SKILL.md` — the workflow, if one matches.
5. `ai-specs/agents/<persona>.md` — the role, if a persona is in play.
6. This document, when extending the harness itself.

Before implementing or applying a change, run `/pipeline-preflight`, which runs the
gates in §7 plus the manual checks that cannot be automated.

Standards that are *not* in this repository: the frontend (React Native) is a
separate project and consumes `docs/api-spec.yml` as its contract. Do not look for
frontend sources here.

## 2. Layers

| Layer | Canonical | Exposure | Rule |
|---|---|---|---|
| Entry | `README.md` | `ai-specs/specboot-instructions.md` | symlink, intentional — see §3 |
| Standards | `docs/base-standards.md` | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `codex.md` | symlink |
| Context | `openspec/config.yaml` | none (read directly) | single file |
| Skills | `ai-specs/skills/<name>/SKILL.md` | `.opencode/skills/<name>/`, `.claude_example/skills/<name>/` | symlink |
| Agents | `ai-specs/agents/<name>.md` | `.claude_example/agents/<name>.md` (gitignored, see §5) | symlink |
| Specs | `openspec/changes/<name>/` in flight, `openspec/specs/` shipped | none (read directly) | real files |
| Cross-project doctrine | `ai-specs/skills/<name>/SKILL.md`, marked cross-project in the declared tree | `.opencode/skills/<name>/` | symlink; guards in `tests/test_skill_agnosticism.py` |
| Deployment doctrine | `ai-specs/skills/deploying-backend-vps/SKILL.md` | vendored copy in the sibling project | see §6 |
| Gates | `Makefile` targets | none (invoked directly) | real file; `gate` is what CI runs |
| Workflow commands | `.opencode/commands/pipeline-preflight.md` | none (invoked directly) | real file, authored here |
| Vendor commands | written by the OpenSpec CLI | `.opencode/commands/opsx-*` | see §5 |
| Harness map | `ai-specs/harness-ia.md` (this file) | none | real file |

Two command surfaces exist and the distinction matters when editing:
`opsx-*` is CLI output and must never be hand-edited, while `pipeline-preflight.md`
is authored here and must be. Nothing else is allowed in `commands/`.

## 3. The entry point is the README, and that is deliberate

`ai-specs/specboot-instructions.md` is a symlink to `../README.md`. This was
installed deliberately when the harness was first set up: the project README *is*
the specboot instructions. Do not "fix" it by replacing the symlink with a copy.

Two consequences follow, and they are the rule:

- **One entry point, not two.** A human and an agent start from the same document,
  so the setup an agent reads can never be a variant of the setup a human follows.
- **Agent-only instructions do not go in the README.** Because the README is
  rendered for humans, anything meant only for agents goes in a skill or in this
  document. A line added to the README to steer agents is a line a human has to
  read and interpret.

The failure mode to know about: an edit to `README.md` changes agent behaviour with
no other file in the diff. When you change the README, check whether the change
also alters what an agent is instructed to do, and say so in the commit.

## 4. Adding a skill, agent, or command

1. Author it under `ai-specs/` (`ai-specs/skills/<name>/SKILL.md` or
   `ai-specs/agents/<name>.md`). Never author it inside `.opencode/` or
   `.claude_example/`.
2. Expose it to each agent with a **relative** symlink from the agent's folder:
   `.opencode/skills/<name> -> ../../ai-specs/skills/<name>`.
3. Add the entry to the `ai_specs_structure` block in `openspec/config.yaml`. That
   block is a declaration; if it drifts from the tree, the declaration is the bug.
4. Use the `sync-agent-symlinks` skill to reconcile all agent folders at once, and
   `writing-skills` to check the skill before it is exposed.
5. Verify nothing was copied: `find .opencode .claude_example -maxdepth 2 -type d
   -name '*-*'` should list vendor directories only, never a skill you authored.

## 5. Vendor directories, and the two harness surfaces

Two surfaces exist, and they are **not** equivalent. Confusing them produces most of
the confusion people have with this harness.

**Committed surface: `.opencode/`.** Tracked in git (22 files). Its
`skills/openspec-*` and `commands/opsx-*` are written by the OpenSpec CLI and
carry a `generatedBy` frontmatter field. They are regenerated by the tool, never
authored by hand:

```bash
openspec --version              # record this
openspec update --force         # rewrites .opencode/ to that version
```

The tool detects agents it can find on the machine. It updated `.opencode/` and
reported `Tools: OpenCode` — it does not know about `.claude_example/`.

**Untracked surface: `.claude_example/` and `openspec_example/`.** `.gitignore:10`
excludes `**/.claude_example/` and `**/openspec_example/`, so nothing in them
reaches the repository. They are a local convenience copy for agents that are not
opencode. Consequences:

- A fresh clone has no `.claude_example/`. Any symlink pointing into it is absent
  on every other machine, so it is not a portable exposure path.
- It drifts silently and has no owner. Measured on 2026-09-27: 10 skills at
  `generatedBy: 1.3.1` against the CLI's 1.4.1, 10 commands against `.opencode`'s
  5, and `openspec-propose` present in `.opencode` but missing from
  `.claude_example` entirely.
- The two differ in more than version. The tool emits Claude's slash syntax
  (`/opsx:explore`) in one and opencode's (`/opsx-explore`) in the other, so a
  single shared file cannot serve both.

**Do not** adopt the `openspec-*` skills into `ai-specs/`. They are tool output
whose source of truth is the CLI. Canonicalising them would put the harness in a
fight with the tool on every upgrade, and would lose the per-agent command syntax.
Reinstall; do not restructure.

**Do** check the two sets after a tool upgrade, and regenerate the untracked copy
rather than patching it. Treat a version mismatch as a local cleanup task, not a
repository defect.


## 6. The deployment doctrine, and how it reaches other projects

`ai-specs/skills/deploying-backend-vps/SKILL.md` is the canonical statement of how
a backend is deployed onto the shared VPS estate. It is written in the generic
"any backend" voice so that a second project can adopt it.

Other projects take a **vendored copy**, not a symlink and not a submodule:

- A cross-repository symlink resolves only on a machine that happens to have both
  clones at the expected relative layout. Elsewhere it is a dangling link, which
  fails at open time — worse than a stale copy, because a stale copy is readable
  and a broken link is not.
- Copy the file, and record the source (`repository`, `path`, and the 40-character
  commit sha) in a header at the top of the copy. A test or a review step should
  compare the recorded sha against the canonical file, so a stale copy announces
  itself instead of quietly diverging.
- A submodule is the alternative when the receiving project must never lag. It
  costs an update step on every clone; prefer the vendored copy unless the doctrine
  is load-bearing for correctness.

The doctrine's two planes — provisioning is an admin action on the shared estate,
migrations are a one-shot job from the app's own source — are described in that
skill. Several independent applications in this estate share that skill; they use
different stacks, schemas, and credentials, and they differ only in their migration
adapter. A skill written for one of them must stay agnostic to all of the others:
state the doctrine, then give the per-stack equivalents in a table, and never bake a
concrete container name, database name, role name, or domain concept into the shared
text. The per-project instances live in each project's own `infra/` directory, where
they can be concrete without becoming wrong elsewhere.

## 7. Quality gates, and the one command that matters

`Makefile` is the executable form of `ai-specs/skills/defining-project-quality-gates`.
Two rules make it the authority rather than a convenience:

- **`make gate` is exactly what CI runs.** `gate-ci` delegates to it rather than
  duplicating it. If CI ever runs something else, the pipeline becomes a second
  unguarded copy of the rules and it is that copy which drifts.
- **Each gate fails loudly and stops at the first failure.** A gate reporting many
  problems at once gets them fixed in batches, and the later ones are forgotten.

| Tier | Target | Time | What it protects |
|---|---|---|---|
| 0 | `make setup`, `make check-env` | minutes, once | the environment is usable at all |
| 1 | `make harness` | seconds | the harness itself — exposure, declared tree, skill portability |
| 1 | `make contracts` | seconds | OpenSpec artifacts, and the exported OpenAPI specification is not stale |
| 1 | `make test` | minutes | the unit tier |
| 2 | `make gate` | minutes | all of the above, in order |

Two implementation details that are easy to get wrong and produce a target that
looks broken for unrelated reasons:

- **pytest runs as `python -m pytest`, never as the `pytest` script.** The script
  form puts pytest's own directory on `sys.path`, not the project root, so
  `import app` fails in `tests/conftest.py`.
- **`export_openapi.py --check` needs `PYTHONPATH=.`** for the same reason: running a
  file inside `scripts/` puts `scripts/` on the path instead of the root.

`docs/api-spec.json` and `docs/api-spec.yml` are generated artifacts. `--check`
exists so a gate can fail on staleness; without it the script would rewrite the
file and exit zero, which is a gate with no way to fail.

## 8. OpenSpec workflows, and where they are decided

The `opsx-*` commands and `openspec-*` skills are written by the OpenSpec CLI, and
**which** ones it writes is decided by a machine-global file:

```
~/.config/openspec/config.json     ← custom_workflows, outside this repository
```

That is a real reproducibility gap, and it is worth stating plainly rather than
papering over: a fresh clone on a new machine will regenerate a different command
surface unless someone has already configured theirs. Two consequences:

- `.opencode/workflows.txt` records the set this repository requires, so a
  divergence is visible instead of silent.
- `tests/test_harness_integrity.py` asserts the installed commands cover that set,
  so the gap is caught when it happens rather than discovered when a command
  refuses to run.

The fix is a project-level config the CLI can read, which the CLI does not currently
support. Until it does, the honest position is: **the repository pins what it needs
and guards it; it cannot yet pin how it is installed.** Do not describe the command
surface as reproducible.

## 9. Gaps: resolved and open

Resolved, so nobody re-diagnoses them. All in the 2026-10-01 pass.

- **`docs/base-standards.md` referenced `opsx:continue` and `opsx:ff`, which did not
  exist.** Enabled and regenerated them; recorded in `.opencode/workflows.txt` and
  guarded (§8).
- **`ai_specs_structure` listed `openspec-sync-specs` as canonical** — it is vendor
  output, not in `ai-specs/` — and omitted `deploying-backend-vps`, `scripts/`, and
  every skill added since. Corrected, and now guarded by a test that fails on drift.
- **`ai-specs/agents/` had no committed exposure.** `.claude_example/agents/` is
  gitignored (§5), so the personas were reachable on exactly one machine. Exposed
  through `.opencode/agent/` as relative symlinks.
- **Nothing guarded the harness.** Added `tests/test_harness_integrity.py`: exposure,
  relative symlinks, declared tree, vendor ownership, frontmatter quality, local
  references, and rejection of authored copies or untracked exposure surfaces.
- **Two skills were pointers, not procedures.** `meta-prompt` was a prompt template
  and `update-docs` a 13-line stub; `code-auditing` had the description
  "Task-focused project skill", which states nothing about when to load it. All three
  rewritten, and the frontmatter and body are now asserted by the harness guard.
- **`docs/api-spec.json` was stale** — two implemented endpoints were missing from it.
  Regenerated, and `--check` added so a gate can catch the next occurrence (§7).
- **There was no CI, no pre-commit, and no gate command at all.** `make gate` is now
  the single entry point, and `pipeline-preflight` runs it plus the manual checks
  that cannot be automated.

Still open. These need a decision or work outside this repository.

- **`docs/base-standards.md` §5 still names `.claude_example` as an exposure path**
  for new agents and skills, which `.gitignore:10` excludes. §5 is now partly
  superseded by this document, which names `.opencode/` as the committed surface, but
  the two disagree and only one is loaded automatically. Reconciling them is a
  policy call.
- **The OpenSpec CLI reads only machine-global configuration** (§8). Until it accepts
  a project-level config, command installation is not reproducible from the
  repository.
- **`.claude_example/` is two OpenSpec versions behind** (§5). Local cleanup.
- **No pre-commit hook, so nothing runs before a commit locally.** `make gate` is
  manual. A hook would catch it earlier but slows every commit.
- **Agent frontmatter is Claude-shaped** — `model: sonnet`, Claude tool names,
  `color`. The personas are readable, but opencode will not honour those fields.
  Needs either a portable frontmatter subset or a per-agent adapter.
- **The VPS compose file builds on the target and uses mutable tags**
  (`infra/vps/docker-compose.yml`). `promoting-a-build` describes the fix; adopting
  it means producing an image on one host and running that artifact on another, which
  needs registry or image-transfer infrastructure this estate does not have yet.
- **No health or readiness endpoints.** `app/main.py` has none, so the functional
  gate in `verifying-a-deployment` currently has nothing to call. `observability-and-slo`
  specifies the two that must not be conflated.
- **No staging environment.** The substitute is running the built image locally with
  production settings, as `dev-environment-parity` describes.
- **Frontend and shared-infrastructure adoption is deferred** — see §10.

## 10. Deferred adoption, and what unblocks it

Two consumers of this doctrine are deliberately not yet using it. Both are recorded
here so the deferral is a decision with a condition rather than a silent omission.

**The frontend** (the sibling React Native repository) consumes
`docs/api-spec.yml` as its contract but does not yet adopt the cross-project skills.
Unblocked when the frontend is opened for harness work: symlink the same
`ai-specs/skills/` set into its own agent folders, run
`tests/test_skill_agnosticism.py` there, and keep `docs/api-spec.yml` as the single
generated contract on both sides.

**The shared infrastructure** — one PostgreSQL and one MinIO serving several
applications — currently lives in concrete form under `core/`. The doctrine is
already written for it (`deploying-backend-vps` covers tenancy, roles and media), but
the split between the estate's own artifacts and this project's instance of them has
not been made. Unblocked when the estate is extracted: canonicalise the shared
provisioning doctrine, keep the per-instance names in the estate's own `infra/`, and
leave the application repositories holding only a vendored copy with a recorded sha
(§6).

Neither deferral blocks the backend, and neither should be started speculatively —
both need the other repository to be open anyway.

