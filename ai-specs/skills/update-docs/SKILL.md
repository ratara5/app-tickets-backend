---
name: update-docs
description: Use after implementing or changing anything, when documentation may now be out of date, when a change alters an API contract, a data model, a configuration key or a deployment procedure, or when about to archive a change. Determines which documents the change actually invalidated, updates those, and leaves the rest alone.
---

# Update Documentation

**Input**: the change that was implemented — its specification, its diff, and the
files it touched — and the project's documentation index.

**Core principle**: update the documents the change **invalidated**, and no others.
Documentation rot comes from two equal causes: a change that was not documented, and
a document rewritten when nothing invalidated it. The second is worse, because it
produces confident text nobody verified.

## When to Use

- After implementing any change that alters observable behaviour.
- When an endpoint, request or response shape changed.
- When the data model changed.
- When a configuration key was added, renamed or given different semantics.
- When a deployment or operational procedure changed.
- Before archiving a change, as a completion gate.
- When a document is found to contradict the code.

## The decision procedure

Work through the change's diff, not through the documentation index. The index
tells you what exists; the diff tells you what broke.

| The change did this | These documents are invalidated |
|---|---|
| Added, removed or altered an endpoint | the API contract; the data model if the shape changed |
| Added, renamed or removed a field | the data model; the API contract; anything documenting the field |
| Changed a validation rule or a status code | the API contract; any example or guide showing the old behaviour |
| Added, renamed or removed a configuration key | the environment example; the configuration reference; any script or guide that sets it |
| Changed a deployment or provisioning step | the deployment guide; the deployment skill if it states the doctrine |
| Changed a mandatory step in the workflow | the standards; the workflow document |
| Changed a generated artifact's source | the generated artifact, by regenerating it — never by editing it |
| Changed only internals, with no observable difference | nothing |

The last row is the one that gets skipped. Most internal changes invalidate no
documentation, and a rewrite is pure risk.

## Rules

- **Never edit a generated artifact by hand.** Regenerate it with the command in its
  own header. A generated file edited by hand is read by the next person as
  hand-maintained, and it diverges silently.
- **Never document behaviour the code does not have.** If the documentation is being
  written to describe intended behaviour rather than implemented behaviour, that is a
  different task, and it belongs in the specification.
- **Update the example, not just the description.** An example that no longer runs is
  worse than no example, because it is trusted.
- **Prefer the smallest accurate change.** Adding a paragraph to a correct document
  is a review problem; rewriting a correct document is a merge conflict and a chance
  to introduce an error.
- **Record what the change invalidates while implementing**, not afterwards. The
  list is obvious during the work and unrecoverable a week later.
- **Do not document what the code already states clearly.** Documentation earns its
  place by carrying what a reader cannot derive: intent, the reason for a decision,
  the failure mode, the procedure.

## The generated-artifact rule, expanded

This repository contains generated files — a schema snapshot, an exported API
specification, a report. They have a different failure mode from hand-maintained
ones: nobody regenerates them.

For each:

- [ ] Identify it as generated, by its own header. If the header is missing, that is
      the first defect to fix.
- [ ] Regenerate with the recorded command, not with an editor.
- [ ] Verify the regeneration is idempotent: run it twice, and the second run
      produces no change.
- [ ] Confirm the header still records its provenance, so staleness is detectable
      after a later commit.
- [ ] Never let a hand edit survive a regeneration. If the file must be edited, the
      edit belongs in its source.

## When documentation and code disagree

Do not assume the code is right. Determine which one is intended, then make the
other match.

| Situation | Do this |
|---|---|
| Code is wrong, documentation is right | fix the code; the documentation was the specification |
| Code is right, documentation is stale | update the documentation |
| Both are defensible, the intent is unclear | stop and ask. This is a design decision, not a documentation task |
| The document describes a behaviour that was removed deliberately | remove the text, and note the removal where readers would look |

The third row matters. Choosing silently resolves a product question, and the
documentation then records the answer as though it had always been intended.

## Verification

Before declaring the update done:

- [ ] Every entry in the decision table above that applies has been handled.
- [ ] Every command, path and key named in the changed text actually exists.
- [ ] Code blocks in the changed text were executed, not read.
- [ ] Generated files were regenerated, not edited.
- [ ] The documentation index lists every new file. A file that exists and is not
      indexed will not be found.
- [ ] No unrelated document was touched.

## Anti-patterns

- Rewriting a correct document because the change was nearby.
- Documenting a feature that is not implemented, in a document read as describing
  what exists.
- Adding a "recently changed" section, which becomes the only part anyone reads.
- Restating what the code says in prose that will drift.
- Fixing an unrelated typo in a document that is otherwise correct, which puts a
  correct document into review for no reason.
- Editing a generated file instead of regenerating it.
- Updating documentation *after* archiving, when the change is no longer in context.

## Interaction with the specification workflow

Documentation is part of the change, not a follow-up to it:

1. The specification states the intended behaviour, including what will be
   documented.
2. The tasks include the documentation update, so it is not forgotten under pressure.
3. The implementation updates the documents as it goes.
4. Archiving confirms the documentation was updated — it is a completion gate, and
   archiving a change whose documentation is stale records a shipped state that does
   not exist.

The failure this prevents is specific: a change is archived, and three weeks later
someone follows a document describing the previous behaviour, because the update was
the one task that had no failing test and therefore no forcing function.
