# Harness Assembler (Meta)

This is a meta-document for assembling/maintaining the agent harness. It defines archetypes, minimal surfaces, and role→skills mapping. Agents do not need to load this on every run; maintainers use it when creating/extending harnesses.

## Archetypes

| Archetype | Projects | Primary agents | Notes |
|---|---|---|---|
| Backend-only | app-tickets-backend | backend-developer, infrastructure-developer (optional), product-strategy-analyst (optional) | Focus on NestJS/FastAPI + DB + APIs |
| Fullstack-monorepo | dopamine-ecosystem/customer-portal | backend-developer, frontend-developer, infrastructure-developer (optional) | Both packages in same repo; keep contracts explicit |
| Infra-provider | GoogleCloudProjects | infrastructure-developer | Shared PG/MinIO, tenancy, backups, ops gates; OpenSpec surface still useful |

## Minimal harness surface per archetype

All archetypes must keep:
- Entry: README + specboot symlink
- Standards: docs/base-standards.md + agent entrypoint symlinks (AGENTS.md/CLAUDE.md/codex.md/GEMINI.md)
- Context: openspec/config.yaml with ai_specs_structure
- Canonical: ai-specs/{agents,skills,scripts,harness-ia.md}
- Exposure: .opencode/{agent,skills,commands} with relative symlinks (skills/agents)

## Role → skills (recommended minimal set)

Keep role.md files as the source of truth for persona/behavior. Use this matrix to decide which skills to include per project (don't strip shared skills unless strictly necessary - current shared model is simpler and test-enforced).

### backend-developer (core)
- code-auditing
- commit
- openspec-apply-change / openspec-continue-change / openspec-verify-change (OpenSpec flow)
- show-spec-working
- update-docs
- using-git-worktrees
- writing-skills

### frontend-developer (core)
- commit
- show-spec-working
- update-docs
- using-git-worktrees
- writing-skills

### infrastructure-developer (core)
- defining-project-quality-gates
- deploying-backend-vps
- dev-environment-parity
- observability-and-slo
- promoting-a-build
- verifying-a-deployment
- update-docs

### product-strategy-analyst (core)
- enrich-us
- explain
- meta-prompt
- triaging-spec-debt

## Assembly checklist

1. Create ai-specs/{agents,skills,scripts}
2. Copy role.md files needed for archetype; keep canonical under ai-specs/agents
3. Copy shared skills (or subset). Prefer keeping full shared set to avoid drift
4. Add entrypoints + symlinks (relative)
5. Write openspec/config.yaml with correct context/ai_specs_structure
6. Add harness-ia.md + specboot symlink
7. Install opsx commands + workflows.txt (CLI-generated surface)
8. Run harness integrity + skill agnosticism tests

## Notes
- Keep role.md files intact (persona/behavior). Assembler is about composition, not replacement.
- Prefer "include necessary + shared" over aggressive trimming - reduces maintenance.
- Expose only via .opencode/ (committed). .claude_example/ is untracked per base-standards.
