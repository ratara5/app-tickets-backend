---
description: Where this repository's agent rules come from, and the standards specific to it.
alwaysApply: false
---

# Base standards

The general rules this repository's agents follow are **generated** from the
harness into the entrypoints: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `codex.md`
and `.cursor/rules/agent.mdc`. Every one of them carries a `GENERATED` header.

Do not edit a generated entrypoint or anything under `.claude/`, `.opencode/`,
`.cursor/`, `.codex/` or `.gemini/`. Change the harness, or change `.agentic.yaml`
and run `agentic sync`; the next sync overwrites the rest. `agentic sync --check`
is the drift gate.

This file is for what is **specific to this repository**, and it is safe to edit.

## This repository's standards

- [Backend standards](backend-standards.md) — API, database, testing and security
  conventions for this service.
- [Frontend standards](frontend-standards.md) — the mobile client.
- [Documentation standards](documentation-standards.md) — how the documents here
  are structured and maintained.
- [OpenSpec mandatory steps](openspec-tasks-mandatory-steps.md) — required steps
  when creating or updating an OpenSpec `tasks.md`.
- [Data model](data-model.md) — entities, relationships and ownership.

## A note on what changed

This repository used to keep reusable agent artifacts in `ai-specs/` and expose
them to each agent tool with relative symlinks. The harness replaced that: the
projection writes real files into each target's directory, records a sha256 for
each in `.agentic.lock`, and refuses to write through a symlink. There are no
agent symlinks left, and `ai-specs/` is gone. Upgrade and rollback are an edit to
`harness:` in `.agentic.yaml` followed by `agentic sync`.
