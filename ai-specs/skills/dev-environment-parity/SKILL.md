---
name: dev-environment-parity
description: Use when a developer's local setup differs from the deployed runtime, when a defect reproduces locally but not on a server or reproduces on one machine and not another, when onboarding a developer or an agent to a project, or when deciding whether to containerize the development environment. Covers the trade-off between native and containerized local execution, seeding without production data, and hot reload that does not exhaust the host.
---

# Development Environment Parity

**Input**: the project root, how the service runs when deployed, and how it runs
locally today. If the deployed topology is unknown, read the deployment
configuration rather than asking — it is usually recorded.

**Core principle**: the value of a local environment is proportional to how closely
it resembles the deployed one. Parity is bought where defects actually come from —
packaging, configuration resolution, dependency versions, network boundaries — and
not where it is merely tidy.

This skill is tool-independent. The mechanisms differ per stack; the trade-offs do
not.

## When to Use

- A defect reproduces locally but not on a server, or the reverse.
- Onboarding a developer or an agent to the project.
- Deciding whether to move from native local execution to containers.
- A change works for one person and not another on the same revision.
- The local environment is missing something the deployed one has — a dependency
  service, an extension, a file the image includes.

## The four axes, which are independent

Almost every "works on my machine" failure is one of these four, and they are
frequently conflated.

| Axis | Local today | Deployed | Parity is worth it when |
|---|---|---|---|
| **Packaging** | native process | container image | the defect is a missing file, a wrong user, or an unwritable path |
| **Dependency versions** | resolved at install time | pinned in the image | the defect involves a library version or a transitive dependency |
| **Configuration resolution** | a local file | injected at runtime | the defect is a default being used, or a value overridden |
| **Network boundary** | everything on the host | separate namespaces, names resolved by a network | the defect involves a hostname, a loopback address, or a published port |

Ranked by how often each is the actual cause: configuration resolution, then
dependency versions, then the network boundary, then packaging. Packaging is the
most-discussed and the least frequent — which is why a team can spend months
containerizing and still not fix the defect they started for.

## The trade-off, stated honestly

Neither mode is wrong. They are different trades, and the honest version of the
argument matters more than the fashionable one.

| | Native local | Containerized local |
|---|---|---|
| Startup time | seconds | seconds to a minute, depending on the image |
| Debugging | direct: breakpoints, a profiler, a shell in the process | one layer removed; attach to the container |
| Iteration on dependencies | immediate | rebuild or a mounted volume |
| Reproduces the deployed packaging | **no** | **yes** |
| Reproduces the deployed network | no | yes |
| Resource cost | low | a database, a queue and a cache per developer |
| Disk | small | large, and grows per project |

**The recommendation, and its condition**: containerize when the defects you
actually encounter are packaging, dependency or network defects. Stay native when
they are logic defects — the debugging cost of containers is paid on every
iteration, and it buys nothing for a pure logic bug.

Most projects need both, and the split is by purpose rather than by doctrine:

- **Native** for the inner loop: running the service, its tests, its type checker.
  Fast, debuggable, and where the work happens.
- **Containerized** for the dependencies and for the pre-production check: the
  database, the object store, the queue, and the run of the actual shipped image
  before release.

That split gets most of the parity benefit for a fraction of the cost, and it is
the arrangement the two other skills in this set assume: `promoting-a-build` covers
running the real artifact, and `verifying-a-deployment` covers proving it works.

## The structure that works

One base definition, plus an override for development. The base is what ships; the
override is what a developer adds. The value is that the base cannot accumulate
development-only settings, because it is also the deployed definition.

```yaml
# base — the definition that ships
services:
  api:
    build: { context: ., target: runtime }
    environment:
      <one variable per required setting, no defaults>
    depends_on:
      db: { condition: service_healthy }

# development override — bind-mounted source, a dev command, published ports
services:
  api:
    build: { target: dev }
    volumes: ["./src:/app/src"]
    command: <the watch/dev command>
    ports: ["<host>:<container>"]
```

The healthcheck on each dependency is not optional. `depends_on` without a condition
starts the application before the database is accepting connections, which produces
a first-run failure that looks like an application bug and is not one.

### Pin what the deployment pins

A base image tag that moves, or a dependency resolved at install time, makes the
local build differ from the deployed one for reasons that have nothing to do with
the code. The local environment is only a parity check if it consumes the same
pinned inputs. This is the single most common reason a containerized local
environment still fails to reproduce a deployed defect.

### Dependencies: image or volume, decided deliberately

| Where dependencies live | Use when | Cost |
|---|---|---|
| baked into the image | fast, isolated, reproducible | a rebuild to change one |
| a mounted volume | the inner loop changes them often | the host and the image can disagree |

The failure mode of the volume is that the image's declared version and the volume's
actual version drift apart, and the local environment stops representing the image.
Whichever is chosen, the same command that resolves dependencies must be the one
used to build the image.

## Configuration parity

The most productive part of parity, and the cheapest. Three rules:

1. **One code path reads configuration.** The application reads its settings the
   same way in every environment. A branch that reads a different file in
   development is a branch that will be wrong somewhere.
2. **Every setting is required in every environment.** A default is a value that
   will be used without anyone deciding to. It is the most common cause of an
   environment starting successfully with a wrong value.
3. **The same file is used locally and in deployment, with different values.** A
   separate local configuration file means the deployed one is never read locally,
   so a rename or a required key is discovered in production.

Log the resolved configuration at startup. It is the fastest way to answer "which
value is it actually using", which is otherwise unanswerable from outside the
process.

## Seeding, and the data rule

A local environment must contain **no production data**. Not a copy, not an
anonymized copy, not "just for testing". Two reasons: it is a data-protection
obligation, and a database with real rows makes a developer's environment
irreproducible, because the answer to a question then depends on what happens to be
in there.

Seed with generated data, deterministic where possible:

- **Deterministic** seed: the same data every time. A defect that reproduces once
  reproduces always, which is the entire point of having a local environment.
- **Structurally faithful** data: the shapes, ranges and relationships the code
  must handle, including the awkward cases — long strings, boundary numbers,
  optional fields absent, unicode.
- **Never** credentials. Local authentication uses local credentials, and a real
  credential in a local environment is a real credential in version control.

Seed volume is a design question, not a convenience. A thousand rows exercises
pagination and index behaviour; ten do not.

## Hot reload that does not exhaust the host

File watching fails in a specific and confusing way, and the cause is worth stating
because the fix is not obvious to someone who has not hit it.

A recursive watcher that follows the whole working directory — including the
dependency directory, the build output and the version-control metadata — will
exhaust the operating system's per-user watch limit. The symptom is an error about
the file-descriptor or watch limit at startup, often after a dependency install
rather than after a code change, so it appears unrelated to the cause.

Three mitigations, in order of preference:

1. **Scope the watcher to the source directory.** The only directories that change
   during development are the source ones.
2. **Exclude the heavy directories** if the watcher cannot be scoped — the dependency
   directory, build output, and version-control metadata.
3. **Raise the host limit** only if the first two are impossible. It is a host-wide
   setting, so it hides the real problem on that machine and does nothing for the
   next developer.

The same exhaustion appears in containerized setups, where the bind mount forwards
events from the host and the count is the host's.

## Onboarding, which is the actual return

Parity is worth what it saves in onboarding, and onboarding is where a project's
real complexity becomes visible: a setup that takes an afternoon is a setup that
excludes people, and the cost of that exclusion is paid in slow reviews and
unfamiliar code.

An onboarding path is complete when a new person or agent can go from a clean
checkout to a working, tested local environment **using a documented command**, with
no undocumented manual step.

- [ ] One documented command creates the environment.
- [ ] One documented command starts everything it needs.
- [ ] One documented command runs the full test suite.
- [ ] Every required setting is named in the example configuration file, with a safe
      placeholder value.
- [ ] Nothing in the setup requires knowledge that is not written down.
- [ ] The setup was executed from a clean checkout by someone who had not done it
      before. **This is the only real test of an onboarding path.** Following your
      own instructions on your own machine is not a test, because you fill the gaps
      without noticing.

The last item is the one that gets skipped and the one that matters. Every
undocumented step is invisible to the person who wrote it down.

## Guardrails

- Never use production data locally, in any form.
- Never put real credentials in an example configuration file, a fixture, or a seed.
- Never let the development override change anything the deployment depends on. If
  the base file is edited to make local development work, the base is no longer
  what ships.
- Never let a local default stand in for a required setting. A default is a value
  nobody chose.
- Never resolve dependencies differently in the local environment than the image
  does.
- Never scope a file watcher to a directory that contains dependencies or build
  output.
- Never call an onboarding path complete without executing it from a clean checkout.
