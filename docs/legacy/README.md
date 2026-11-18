# Legacy consumer documents

These documents were kept for history after the harness took ownership of the
rules they described. They are not operational guides.

| Document | Why it is here |
|---|---|
| `harness-ia.md` | The pre-migration topology, when `ai-specs/` was canonical and agent folders held symlinks. The harness now owns the map: `docs/ARCHITECTURE.md` in the harness checkout. |
| `harness-assembler.md` | The old assembler for the `ai-specs/` layout. Its content became the harness catalog (`manifest.yaml`), and the `legacy-seed-removal` skill removed the seed. |
| `ADOPTION_STEPS-1.14.0.md` | The one-off upgrade runbook written for 1.14.0. It was superseded by the 1.15.0 upgrade on 2026-11-18; the canonical procedure is `docs/ADOPTION.md` in the harness checkout. |

The consumer's current, operational documentation stays in `docs/`:

- `deployment-guide.md` — the concrete VPS deployment instance.
- `deploy-vps-ai-harness.md` — the pointer to the `deploying-backend-vps` skill.
- `learned-lessons.md` — the incident and failure record.
- `openspec-tasks-mandatory-steps.md` — the consumer's declared task steps.

A document is moved here when its generic content is owned by the harness and its
remaining value is historical. Do not add a new operational guide here; write it
in `docs/` or in the harness.
