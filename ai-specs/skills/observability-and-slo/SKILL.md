---
name: observability-and-slo
description: Use when a service is hard to diagnose in production, when an outage or performance problem had to be investigated from logs alone, when an alert fired with no actionable information, or when deciding what to measure and what to alert on. Covers instrumenting a service so a specific failure can be confirmed from its own signals, defining service level objectives from user-visible behaviour, and writing alerts that are actionable rather than noisy. Deliberately starts with logging and health checks, not with a metrics vendor.
---

# Observability and Service Levels

**Input**: the service's externally visible behaviour — its endpoints, its
dependencies, and what a user is actually trying to accomplish.

**Core principle**: observability exists to answer one question — *is the service
working for users right now?* Instrumentation that cannot answer that is cost
without benefit. This skill starts with structured logging and honest health checks,
because those carry most of the diagnostic value and require no vendor.

## When to Use

- A production problem was diagnosed from application logs alone, or not at all.
- An alert fired and the first thing the responder did was silence it.
- Nobody knows whether a slow response is the application, the database or the
  network.
- Deciding what to measure, and what to wake someone for.
- Before defining a service level objective, or after an incident that showed the
  existing objective was wrong.

## What to actually build

A defensible order. Each rung is strictly more useful than the one above it for the
same money, and each is optional only if the one below it works.

| Rung | Gives | Cost | Build it when |
|---|---|---|---|
| **Structured logs** | what happened, per request, with correlation | hours | always — it is the floor |
| **Health endpoints** | whether the process is up, and whether it can serve | hours | always |
| **Metrics** | rates, errors, durations, saturation, over time | days | there is a question logs cannot answer |
| **Distributed tracing** | which hop is slow, across services | days | the system spans services and logs cannot be correlated |
| **Alerts on objectives** | notification only when users are affected | days | metrics exist and are trusted |

Two failure modes to avoid at the start, because they are the usual outcome of
jumping to the top of the table:

- **Adopting a vendor before instrumenting.** A platform with no meaningful
  instrumentation reports high confidence about nothing. The cost is a dependency
  plus a configuration surface, and the diagnostic value is zero until the
  application emits what the platform consumes.
- **Instrumenting for the framework rather than the user.** Framework-level
  request counters do not tell you whether a user could complete a task.

## Rung 1 — Structured logging

Every request, one record, machine-parseable, carrying enough to reconstruct the
request's outcome without the surrounding context.

Required fields per request:

| Field | Why |
|---|---|
| a request or correlation identifier | to join the request's records, including across services |
| the route, not the raw URL with the path substituted | high-cardinality labels destroy metric storage and leak identifiers into logs |
| method | |
| status | |
| duration | |
| a stable application error code, where one exists | ties a log to a client-visible failure |
| the authenticated actor's identifier, where applicable | never the credential itself |

Rules that matter more than the field list:

- **One record per request, emitted once, in one place.** Logging at the edge of
  every handler produces duplicates and disagreements; the single chokepoint is
  also the only place that sees the real status and duration, including a 500
  raised in a global exception handler.
- **Log the cause, not the consequence.** "Failed to process request" is the
  consequence; "database rejected the migration: relation already exists" is the
  cause, and the second one is what ends the investigation.
- **Never log credentials, tokens, session identifiers, or personal data.** Redact
  at the logging boundary so a future caller cannot forget.
- **Log at the boundary, not inside every function.** Internal logging at every
  layer produces volume that hides the record that mattered.
- **Errors always include the exception and its cause chain.** An error line with
  no traceback is a request for a second incident.

## Rung 2 — Health endpoints

Two distinct questions, and conflating them causes real outages. This
distinction is the single most consequential part of this rung.

| Endpoint | Question | Must it check dependencies? |
|---|---|---|
| **Liveness** | is the process stuck? | **no** — if it does, a failing dependency causes a restart loop across the whole fleet |
| **Readiness** | can this instance serve a request now? | yes — the database, and anything required to serve |

The rule that follows, and it is counter-intuitive: **liveness never checks
dependencies**. A liveness probe that queries the database will restart every
instance when the database is slow, converting a degraded service into an
unavailable one, and the restarts will not fix the database.

Readiness checking the database is correct and has a different consequence: the
instance is removed from rotation rather than restarted, which is the intended
behaviour.

Also, and this is the omission that matters most in practice:

- **Add an endpoint that exercises the real path.** Liveness, readiness and a
  health check that fetches a row from the database through the application's own
  client, not a raw connection. A raw connection succeeds while the pool is
  exhausted, the migration is missing, or the credentials are wrong — which are the
  three failures that actually happen. This endpoint is what
  `verifying-a-deployment` uses as its functional gate, and without it that gate
  can only prove the process is up.
- **Do not expose detailed failure reasons publicly.** A readiness response that
  names the failing dependency is an information leak on an internet-facing port.
  Return a status code and a generic reason; keep the detail in the logs, correlated
  by the request identifier.
- **A health endpoint that is never checked is a liability.** It is untested code
  that returns 200 in the one situation it exists to detect. Add it to the
  deployment gate list so a broken probe fails a deployment rather than a user
  request.

## Rung 3 — Metrics

Instrument what lets a question be answered later without waiting for a problem.
The four families are worth covering because they fail in different ways.

| Family | Question it answers | Example |
|---|---|---|
| **Traffic** | how much is arriving | requests per route per minute |
| **Errors** | how much is failing | failures per route, by stable error code |
| **Duration** | how slow is it | end-to-end request duration, and the slow-path dependency |
| **Saturation** | what is running out | pool utilisation, queue depth, connection count, memory, disk |

Rules:

- **Metrics are aggregatable and labels are low-cardinality.** The route, the
  method, and the status. Never a user identifier, a request identifier, a raw
  path, or an error message. A single high-cardinality label can make the storage
  unusable, and it is not recoverable after the fact.
- **Measure at the boundary and at the dependency.** An end-to-end duration tells
  you the service is slow; a per-dependency duration tells you which dependency is
  responsible. Without both, the investigation is guesswork.
- **A dashboard nobody reads is a cost.** Start with the four families above and
  add only in answer to a real question.

## Rung 4 — Tracing

Only when requests cross service boundaries and a correlation identifier cannot
join the records — which is the usual case when one of the hops does not propagate
it.

The prerequisite, and it is the actual reason tracing usually fails: **the
correlation identifier must be propagated on every outbound call.** If one hop drops
it, the trace is a broken chain, and the tool shows a long request with an
unattributable gap. Fix propagation before adopting tracing.

Sampling should keep the errors and the slow requests and drop the boring
successful ones. Uniform sampling at a low rate will discard exactly the interesting
requests.

## Service level objectives

An SLO is a **target for a user-visible behaviour, measured over a window**. It is
not a metric, and not a threshold on a resource.

Components:

| Component | Meaning |
|---|---|
| the indicator | the user-visible measure — availability of a request, latency of a response |
| the objective | the target over the window, e.g. 99.5% of requests succeed in 28 days |
| the window | the period over which it is measured |
| the error budget | `1 − objective`, as the allowance for unreliability |

Which indicators to define, in order of usefulness:

1. **Availability of the primary operation** — the request a user depends on.
2. **Latency of that operation**, at a threshold that matters to the user. "Fast
   enough" is a product decision, not a percentile choice.
3. **Correctness**, where there is one — a proportion of responses that are
   technically successful and semantically right. Frequently missing, and the most
   honest indicator of the three.

Sizing:

| Indicator | Starting objective | Notes |
|---|---|---|
| Availability of a primary read | 99.5 – 99.9% | lower than people expect; a 99.9% target means a budget of minutes per month |
| Availability of a primary write | 99 – 99.9% | writes are harder to make available than reads |
| Latency | 95th percentile under a threshold | the 99th percentile is dominated by the tail you cannot control |
| Correctness | as high as achievable | a wrong answer is worse for the user than a failed one, and usually invisible |

**Set the objective below what the service can actually deliver**, and measure it
before tightening it. An objective set at 99.99% for a single-instance deployment is
not a target; it is a standing alert, and standing alerts get silenced.

The error budget is the useful part, because it converts a reliability argument
into a delivery-speed decision: **when the budget is exhausted, the next change is a
reliability change.** That rule is what makes an SLO operative rather than
decorative.

## Alerts

An alert is warranted only when **a human must act before users are harmed, and the
action cannot wait for someone to look**.

Everything else is a dashboard or a report. This is the whole discipline, and it is
usually violated by adding alerts rather than by adding too few.

| Situation | Signal |
|---|---|
| Users are affected now | alert — on the SLO burn rate, not on a resource |
| Users will be affected within the alert window | alert — page |
| Users are affected but the fix is routine | ticket |
| A resource is degrading but users are unaffected | dashboard |
| A single instance is unhealthy | dashboard; the scheduler restarts it |

Writing one that works:

- **Alert on symptoms, not causes.** "The error rate is above budget for the primary
  operation" prompts an investigation. "CPU above 85%" prompts a question about which
  CPU and why. Symptom alerts need no hypothesis; cause alerts need one, and cause
  alerts that fire without a hypothesis are noise.
- **Use a burn-rate alert, not a fixed-threshold alert.** A fixed threshold either
  fires constantly or misses slow burns. A burn-rate alert fires when the budget is
  being consumed at a rate that will exhaust it inside the window — fast burn pages,
  slow burn opens a ticket.
- **Every alert has a runbook link, an owner, and a stated first action.** An alert
  without a first action is a notification, not an alert.
- **Test the alert.** Fire it in a non-production environment and confirm a human
  receives it and that the runbook answers it. An alert path that is broken is
  discovered by the incident it was supposed to prevent.

## Order of work

1. One structured log record per request, with a correlation identifier.
2. Liveness and readiness endpoints, with liveness free of dependency checks.
3. **A health endpoint exercising the real path**, wired into the deployment gates.
4. Error codes that are stable and loggable, and that clients can be told about.
5. Availability and latency indicators for the primary operation, measured.
6. An SLO from those measurements, deliberately below the current capability.
7. Burn-rate alerts against the SLO, with runbooks.
8. Metrics for saturation, then tracing — only when a real question needs them.
9. A vendor, only when the above is in place and the remaining gap is genuinely a
   scale or retention problem.

## Anti-patterns

- **Alerting on causes.** CPU, memory and disk as pages. Symptoms, not resources.
- **A liveness probe that checks dependencies.** Converts degradation into an outage.
- **A readiness probe that checks nothing.** Never removes a broken instance.
- **High-cardinality labels.** A user identifier in a label will exhaust metric
  storage, and it is not recoverable.
- **Logs without a correlation identifier.** Turns an investigation into a timeline
  reconstruction by timestamp.
- **Logging personal data or credentials.** Redact at the boundary.
- **An SLO set above demonstrated capability.** Guarantees a permanently firing
  budget alert, which teaches the team to ignore alerts.
- **An error budget that is computed and not used.** If exhausting it does not
  change what gets worked next, the SLO is a dashboard label.
- **Adopting a platform before the application emits anything meaningful.** Cost and
  configuration surface, zero diagnostic value.
- **Percentile averages presented as summaries.** p50 hides the tail; a single
  number called "the average latency" is usually p50 and is usually the wrong
  answer.
- **A dashboard with no question behind it.** Every chart should correspond to a
  question someone actually asks.
