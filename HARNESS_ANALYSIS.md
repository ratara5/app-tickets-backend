# Harness Analysis and Enhancement Plan

## Current State Assessment

The harness in `app-tickets-backend`, `GoogleCloudProjects`, and `dopamine-ecosystem/customer-portal` is already excellent. It follows a consistent, well-structured pattern:
- `ai-specs/` as canonical source
- Relative symlinks to expose agents/skills
- Agent entrypoints (AGENTS.md/CLAUDE.md/codex.md/GEMINI.md) symlinked to `docs/base-standards.md`
- `ai-specs/specboot-instructions.md` symlinked to `README.md` (deliberate design)
- `openspec/config.yaml` with context, standards, implementation, ai_specs_structure
- Opsx surface under `.opencode/commands/` (CLI-generated) vs authored `.opencode/commands/pipeline-preflight.md`
- Harness integrity tests enforce portability and structure

## Key Observations

1. **"harness-assembler.md" doesn't exist yet.** No such file found in any harness. The idea is to have a meta-assembler that composes the minimal harness per project type.
2. **Roles are currently role-based agents**: `backend-developer.md`, `frontend-developer.md`, `infrastructure-developer.md`, `product-strategy-analyst.md`. This works but could be enhanced with an assembler that selects minimal necessary skills per agent/role.
3. **Skillset is broad** (18+ skills) - shared via symlinks. This is good for reuse and portability.
4. **All three harnesses are consistent in structure.**

## Enhancement Proposal: harness-assembler.md

Rather than bloating every agent with all skills, create a `harness-assembler.md` (canonical in `ai-specs/`) that:
- Defines project archetypes: backend-only, frontend-only, fullstack (backend+frontend), infra-provider, monorepo-mixed
- Maps roles -> minimal required skills (by project type)
- Defines minimal harness surface per archetype
- Provides generation checklist (entrypoints, symlinks, config, structure)

### Suggested archetype mapping

**Backend-only (e.g. app-tickets-backend):** 
- backend-developer: needs code-auditing, commit, openspec-apply/change, show-spec-working, update-docs, using-git-worktrees, writing-skills
- frontend-developer: not needed? But present for cross-project awareness
- infrastructure-developer: minimal infra skills if self-hosted
- product-strategy-analyst: as needed

**Fullstack/monorepo (dopamine-ecosystem/customer-portal):**
- backend-developer + frontend-developer + infrastructure-developer (if needed)
- Keep shared skills common

**Infra-provider (GoogleCloudProjects):**
- infrastructure-developer primary
- minimal openspec/ops skills

But the current "pass all skills to all agents via symlinks" is simple and test-enforced. Over-customization adds complexity.

## Recommendation

**Keep the current harness structure - it's excellent.** Add `harness-assembler.md` as a *meta* document (how to assemble minimal harnesses) without forcing all agents to load it. Place in `ai-specs/harness-assembler.md` (canonical). Update `harness-ia.md` read order to mention it when *assembling/extending* harnesses (not on every run).

### Implementation plan (minimal, safe)

1. Create `ai-specs/harness-assembler.md` in `app-tickets-backend` (template with archetypes + role->skills matrix)
2. Symlink/expose as needed (not required to expose via `.opencode/agent/` unless used as agent)
3. Update `harness-ia.md` §6 to mention harness-assembler as meta (for maintainers)
4. Propagate same to `GoogleCloudProjects` and `dopamine-ecosystem/customer-portal` (vendored copy)

This keeps existing excellent structure intact while adding "assembly guidance" for new projects.

## Quick verdict

- Current harness is production-grade and consistent.
- Don't replace role.md files with assembler - keep role.md files as-is (they define persona/behavior). Assembler is about *which* artifacts to include per project.
- "Pass them the necessary role.md" - keep existing agents; optionally trim skills per project type, but current shared approach is simpler and passes tests.
