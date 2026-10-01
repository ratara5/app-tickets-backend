---
description: Run the preflight checks for a pipeline stage, before work begins or before a change is applied.
---

# Pipeline Preflight

Run this before starting implementation work and before applying a change. It
answers one question: **is it safe to proceed right now?**

If any check fails, stop and report. Do not continue and mention it later.

## Usage

```
/pipeline-preflight [stage]
```

`stage` is optional. Without it, run the defaults, which cover starting work.

## What it runs

The automated tiers from the `gate` target, which is the same command continuous
integration runs:

```
make harness     # harness integrity and skill agnosticism guards
make contracts   # OpenSpec artifacts and the exported API specification
make test        # the unit tier
```

`make gate` runs all three. Use it when there is time; use them individually when
the stage needs the answer from one tier first.

## Manual checks

The command above covers what is automatable. These are not, and they are where
preflight usually fails in practice:

- [ ] **The specification is current.** The change being applied has artifacts that
      reflect the current request, not an earlier version of it.
- [ ] **No work is already in flight.** Another change is open with tasks in
      progress, or this one already has a branch with commits.
- [ ] **The change is scoped.** The diff for this work touches only the files the
      change names. A wide diff is the signal that the change is underspecified.
- [ ] **Dependencies are available.** Anything the work needs to run is reachable
      right now, so a failure is unambiguous.
- [ ] **The rollback is known.** If this change ships, the way back is written down
      before the change, not after.

## Reporting

```
## Preflight — <stage>

make harness    ✓ <n> passed
make contracts  ✓ <n> items validated
make test       ✓ <n> passed

Manual:
  specification current   ✓ / ✗
  no work in flight       ✓ / ✗
  scope is bounded        ✓ / ✗
  dependencies available  ✓ / ✗
  rollback known          ✓ / ✗

Verdict: PROCEED | BLOCKED
<for BLOCKED: what failed and what unblocks it>
```

## Related

- `ai-specs/skills/defining-project-quality-gates` — what each tier is for, and
  which tier a change belongs to
- `ai-specs/skills/verifying-a-deployment` — the gates after a deployment, which
  preflight does not cover
- `ai-specs/skills/promoting-a-build` — artifact identity across environments
