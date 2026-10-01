---
name: meta-prompt
description: Use when a request to an agent is likely to produce the wrong thing — when it is vague, when it states a solution instead of a goal, when it omits the constraints that decide the answer, or when the same request has produced inconsistent results across attempts. Rewrites the request so the objective, the constraints and the acceptance criteria are explicit before any work begins.
---

# Meta-Prompt

**Input**: the original request, plus whatever context is already available — the
repository, the project standards, the current state of the work.

**Core principle**: most bad output from a capable agent is not a capability
failure. It is an under-specified request that the agent resolved by guessing, and
guessing silently. The fix is upstream.

This skill rewrites the request. It does not perform the task.

## When to Use

- The request names a **solution** where a **goal** was meant ("add a column" when
  the need is "the seed loader truncates this value").
- The request is one sentence and the acceptance criteria are unstated.
- The same request has produced materially different results on two attempts.
- The request omits a constraint that would change the answer — a stack decision, a
  compatibility requirement, a performance budget, a file that must not change.
- Before a large or irreversible task, where getting the scope wrong is expensive.

**Do not use it** when the request is already precise and the work is routine. The
rewrite costs a round trip and adds nothing.

## The diagnostic: what is missing

Ask these five questions about the original request. Each one whose answer is "not
stated" is a gap the rewrite must close — either by specifying it, or by making it
an explicit question.

| Question | Why the answer changes the work |
|---|---|
| **What outcome is wanted?** | "Improve error handling" and "return 422 with a field-level message" produce different code. |
| **What must not change?** | Unstated, everything is fair game, including files the work was meant to leave alone. |
| **How will it be judged done?** | Without a criterion, completion is a matter of opinion and gets argued. |
| **What is already been tried or ruled out?** | Without it, the agent re-proposes the approach that was already rejected. |
| **What is the scope boundary?** | "Fix the upload path" can mean one function or the whole feature. |

The fourth question is the one most often skipped and the most expensive. An
approach that was already tried and failed — and not recorded anywhere the agent
will read — is retried, and the failure is rediscovered from scratch.

## The rewrite

Produce a prompt with these parts, in this order. Drop any part that would be
empty; do not pad it with restatement.

```
## Objective
One sentence. The outcome, stated as an observable change, not as an activity.
"Not: add a retry. Instead: a transient failure of the object store must not fail
the request."

## Context
What exists now, and the specific facts that constrain the answer. Reference
files, not descriptions of them: the current behaviour, the current structure, the
conventions already in force.

## Requirements
Numbered. Each one independently checkable. "The function must be pure" is
checkable; "the code should be clean" is not.

## Constraints
What must not change, and the boundaries: files out of scope, compatibility
requirements, performance or resource budgets, prohibited approaches and why.

## Acceptance criteria
The observable conditions that decide the work is done. Prefer a command, an
output, or a queryable state over a description. "Running the suite shows no
regressions and the new case is covered" beats "tests pass".

## Out of scope
What this task deliberately does not address, and where it will be addressed
instead. This section prevents the most common form of scope creep, which is
helpfully fixing an adjacent problem noticed in passing.
```

## The techniques, and when each applies

| Technique | Applies when | Avoid when |
|---|---|---|
| **Goal over solution** | the request names an implementation | the implementation is genuinely fixed (a library's API, a spec requirement) |
| **Explicit constraints** | the work could plausibly sprawl | the task is one line in one file |
| **Acceptance criteria as commands** | the result is verifiable | the result is genuinely a judgement |
| **State the anti-goals** | a plausible wrong approach exists | the space has one reasonable path |
| **Concrete references, not adjectives** | always | never — "modern", "clean", "robust" are all uncheckable |
| **Numbered requirements** | more than one thing is asked | a single atomic change |
| **Name the file or module** | the location is not obvious | the location is already given |

The single highest-value edit is usually replacing adjectives with checkable
claims. "Make the seeder robust" becomes "the seeder must refuse a value the target
column cannot represent, and say which value and which column".

## Adapting to this project

When the request touches this repository, the rewrite should reference what already
exists rather than restate the project's rules, because the agent is instructed to
read them:

- The standards are already loaded. Do not paste them into the prompt; name the file
  and the section.
- The specification-driven workflow means "implement" is not a complete instruction.
  Say which change is being implemented, or that a new one is needed first.
- Where a change is being implemented, the prompt should say so explicitly, because
  the workflow requires the artifacts to be updated before the code rather than
  after.
- The deployment path has gates that must be run by the agent, not assumed. Say
  which ones apply.

## Anti-patterns

- **Padding.** A longer prompt that says the same thing is not a better prompt; it
  is a slower one, and the important constraint is now harder to find.
- **Restating loaded context.** If the agent is instructed to read a standard, the
  prompt should cite it, not quote it. Duplicated rules drift apart from the source
  and the agent then follows the stale copy in the prompt.
- **Specifying the solution when you want a judgement.** If the point is to get the
  agent's design, "here is how to implement it" removes the only reason to ask.
- **Over-specifying the mechanism, under-specifying the outcome.** A prompt that
  dictates five implementation steps and leaves the acceptance criteria unstated has
  optimised the wrong variable.
- **Asking for a plan and an implementation at once.** They are different outputs and
  mixing them produces a plan with unrequested code in it.
- **Adding "be thorough" or "think step by step".** These do not improve output and
  they crowd out the actual constraints. Specificity does that work.

## Verification of the rewrite

Before sending it, check:

- [ ] Could two competent people read it and build different work? If yes, a
      requirement is still implicit.
- [ ] Is every adjective replaced by something checkable?
- [ ] Is the acceptance criterion something that can be *run*?
- [ ] Is what is out of scope stated, so the adjacent problems are not absorbed?
- [ ] Does it reference the project's existing files and standards by path instead of
      quoting them?
- [ ] Is it shorter than the work it is asking for? A prompt longer than the task is
      usually specifying the wrong thing.

## Output format

```
## Original
<the request as given, verbatim>

## Gaps identified
<which of the five diagnostic questions went unanswered, one line each>

## Enhanced
<the rewritten prompt, using the section structure above>

## Open questions
<anything the rewrite could not resolve and that genuinely needs a human answer>
```

Keep `## Open questions` short and only include items where a wrong guess would be
expensive. A rewrite that ends with fifteen open questions has not reduced the
uncertainty; it has relocated it.
