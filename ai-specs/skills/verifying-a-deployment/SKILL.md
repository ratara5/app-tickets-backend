---
name: verifying-a-deployment
description: Use when a deployment or release has just happened and its correctness must be established, when a health check passes but the feature is suspected broken, when designing the verification gates for a service, or when deciding whether a check is strong enough to trust. Covers the gate catalog from liveness through functional round-trip, why health checks miss storage and dependency failures, and the rule that a check which passes when it was expected to fail is a defect.
---

# Verifying a Deployment

**Input**: the target environment, the change being verified, and the service's real
dependencies. If the dependency list is unknown, discover it from the configuration
before verifying anything.

**Core principle**: a verification gate is a check with **recorded output**, not an
assertion that something looks fine. If you cannot paste the command and its
output into the release notes, the gate did not run.

This skill is stack- and platform-agnostic. It states what must be proven about a
running service and how to tell a strong check from a weak one. For the
estate-specific tenancy, backup and media procedures, see `deploying-backend-vps`.

## When to Use

- Immediately after any deployment, before declaring it done.
- When a health check is green and a feature is nevertheless reported broken.
- When designing the gates for a new service, or reviewing someone else's.
- Before telling anyone a release is complete.
- When a gate failed and the question is whether the gate or the deployment is at
  fault.

## The weakness this skill exists to correct

**A service that starts is not a service that works.** This is the single most
common verification failure, and it is not a small one, because it produces a
release that is reported successful and is not.

The mechanism is uniform across stacks: the process comes up, the framework's
built-in health route answers, and the check passes. But that route answers about
*the process*, and the process being alive says nothing about whether it can reach
its database, its object store, its cache, or its queue. A container whose storage
host name does not resolve starts perfectly, passes its health check, and fails on
every request that touches storage. The first signal of the outage is a user.

So a gate that only asks "is it up?" is measuring the wrong thing, and it will
report green through an outage.

## Layer 1 — Liveness: is the process running?

The cheapest gate, and the weakest. It answers exactly one question.

- [ ] The process is running and has not crash-looped. Check **restart counts**, not
      just status: a container that has restarted forty times is currently "up" and
      has been failing for an hour.
- [ ] Logs show a completed startup, with no repeated error.
- [ ] It is running as the intended user, not as root. A container that starts as
      root has told you the image's hardening was not applied.

**A restart loop is a failing gate even when the container is up.** `restart:
unless-stopped` turns one crash into an indefinite retry, and the status field will
say "Up" the whole time.

## Layer 2 — Readiness: can it serve traffic right now?

Readiness is a *different* question from liveness, and conflating them causes
outages in both directions:

- If readiness is wired to liveness, a dependency outage makes an orchestrator
  **restart healthy containers**, which does not fix the dependency and destroys the
  evidence.
- If a load balancer sends traffic to a process that is not ready, users get errors
  during a startup that would have succeeded.

- [ ] A readiness check exists and is genuinely separate from liveness.
- [ ] It reflects the dependencies the service cannot work without.
- [ ] It returns a distinct status for "not ready" from the one for "not running".
- [ ] It is fast. A readiness check that takes thirty seconds has added thirty
      seconds to every deploy and every dependency event.

**Not every dependency belongs in readiness.** A cache miss degrades; a missing
primary database does not. Putting a non-essential dependency in readiness converts
a degradation into an outage. This is a judgement call per service, and it should be
made deliberately rather than by adding everything that is reachable.

## Layer 3 — Functional: does it do its job?

This is the layer that catches real defects, and the one most often skipped. It
exercises the actual dependency path with a real request.

- [ ] One request that reaches the primary datastore, returns real data, and
      serializes correctly.
- [ ] One write path, if the service writes: create, read back, and observe the
      effect. A read-only check misses serialization, constraint and transaction
      defects entirely.
- [ ] One path that touches **each** external dependency — object storage, cache,
      queue, third-party API — with a real round-trip, not a connectivity ping.

**The round-trip is the gate, not the reachability.** A TCP connect to a storage
endpoint succeeds while every signed request fails, because signing depends on the
endpoint the *client* will use, and that is a different value from the one the
server dials. When an application produces URLs for a client to fetch, the gate
must fetch one — from outside, over the public path — and read the bytes back.

This is the check that catches the most damaging class of release defect, and it is
skipped more often than any other, because a health endpoint is right there and it
answers.

## Layer 4 — Configuration actually resolved

Services fail on defaults more often than on missing values, and the failure is
silent: the process starts, using a default that is wrong for this environment.

- [ ] The service resolved its own configuration, not a fallback default. Grep the
      startup log for the values it reports.
- [ ] Every endpoint the service **dials** is reachable *from where the service
      runs*. A value that works on the host is a different value inside a container.
- [ ] Every origin the service **signs into URLs** is one the client can resolve. A
      signed URL for an internal name produces a `403`/`404` at the client, and the
      application's own requests keep working, so nothing server-side detects it.
- [ ] Nothing sensitive is baked into the image. Configuration is injected at
      runtime.

**The two-value trap**: an application frequently needs two different addresses for
one dependency — the internal one to dial, and the public one to put in URLs handed
to clients. Forcing a single value to serve both is what produces an outage when
the public address changes. If the application does that today, splitting the value
is a fix, not a refactor.

## Layer 5 — Isolation, when the estate is shared

Applies when the database or object store is shared with other applications. Full
procedure in `deploying-backend-vps`; the verification point here is that it is
verified rather than assumed.

- [ ] The estate's state was snapshotted before the change and diffed after.
- [ ] Nothing belonging to another tenant disappeared.
- [ ] The application's credential cannot reach another tenant's data. Asserted, not
      assumed: try it, and confirm the attempt fails.
- [ ] No data port is exposed publicly.

**A check that passes when it was expected to fail is a defect, not a pass.** This
is the rule that makes the difference between testing a boundary and assuming one.
Listing what a role can see proves nothing, because catalog visibility is not
permission. Assert the capability directly, and treat an unexpectedly successful
attempt as the most serious finding in the whole verification.

## Layer 6 — Observability is actually working

A deployment that breaks monitoring is a deployment that removed its own early
warning.

- [ ] Logs are structured and on stdout, with a request or correlation identifier
      that lets one request be followed end to end.
- [ ] The log fields that matter are present and not silently dropped by a level
      filter.
- [ ] Error tracking receives errors from this environment, and a deliberately
      raised error appears. Untested error tracking is assumed working.
- [ ] The uptime check is pointed at the real public entry point, not at a
      container-local address that answers while the proxy is broken.
- [ ] Alerts would fire for the failure this release could plausibly cause. Verified
      by reasoning about the alert thresholds, not by waiting for one.

## The strength of a check

Not all checks are equal, and the difference is worth stating because teams
substitute one for another:

| Weak | Strong | Why the weak one misleads |
|---|---|---|
| Process is up | Process is up **and** has not restart-looped | status says "Up" during a crash loop |
| Health route returns 200 | Health route returns 200 **and** a functional request succeeds | the route does not touch dependencies |
| TCP connect succeeds | A signed request round-trips | reachability ignores credentials and signature |
| Container started | The intended digest is running | a rebuild can start successfully |
| Command exited 0 | Output was inspected and object counts asserted | scripts exit 0 after partial work |
| Config loaded | Config resolved to this environment's values, not defaults | a default is a valid-looking value |
| It works on my machine | It works with production settings and the real artifact | local config and packaging differ |
| Logs look fine | The specific operation appears in the logs | a failing path may never be reached |
| No errors in 5 minutes | The dependency was exercised at least once | no traffic means no evidence |

## Reporting

A verification is a report, and the report is the deliverable. What it contains:

| Field | Note |
|---|---|
| What was deployed | commit and **digest** |
| Each gate, its command, and its output | output, not a verdict |
| Anything that surprised you | recorded while it is still accurate |
| Gates not run, and why | an explicit gap is acceptable; a silent one is not |
| Rollback readiness | the command, and confirmation the previous artifact exists |

Two habits that pay for themselves:

- **Record the output while it is fresh.** Reconstructing evidence later is guesswork.
- **Write down what surprised you immediately.** A deploy that worked for a reason
  nobody recorded will be re-diagnosed from scratch the next time it fails.

## Guardrails

- Never declare a deployment complete on a liveness check alone.
- Never treat "the container started" as a passed gate.
- Never treat a command's exit status as proof it did the right thing; inspect the
  output and assert the expected result.
- Never accept a check that passes when it was expected to fail. Investigate it as
  the highest-priority finding.
- Never skip the functional check because the service is up. That is precisely when
  it is most likely to be skipped and most likely to be needed.
- Never verify from inside the network only. The public path — proxy, TLS, DNS,
  signature host — is a separate set of failures.
- Never modify a shared resource to make a gate pass.
- Never report a gate as passed without its output.
