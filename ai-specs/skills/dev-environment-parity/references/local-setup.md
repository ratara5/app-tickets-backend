# Local Setup — the concrete arrangement

The arrangement the main skill recommends, expressed for the common cases. Names
are generic; substitute the project's.

## The split, restated

| Runs natively | Runs containerized |
|---|---|
| the service itself, for the inner loop | the database |
| the test suite | the object store |
| the type checker, linter, formatter | the queue, the cache |
| | the built image, for the pre-production check |

The service runs natively because that is where the iteration happens and where
debugging is cheapest. Its dependencies are containerized because they are the
parts most likely to differ from a developer's machine, and because a version
mismatch in a database is invisible until it is not.

## Dependency services

Every dependency the service needs locally, and nothing it does not:

| Service | Why it is needed locally | Notes |
|---|---|---|
| Relational database | the application cannot start without it | pin the **same major version** as the deployment; a minor-version difference is a schema and behaviour difference |
| Object storage | the application fails startup if the store is unreachable | pin the same version; the API surface used is small and stable |
| Cache | optional unless the code paths under test use it | if optional, run without it and see whether the code degrades correctly |
| Queue | only if a background worker exists | a worker with no queue will not start |

**Version pinning is the point.** A developer on a different major version of the
database is not testing parity; they are testing a different system, and the
defects they find are usually not the ones that occur in production.

## Bringing it up

```bash
# start the dependencies, wait until they are actually ready
docker compose -f compose.yaml -f compose.dev.yaml up -d --wait
docker compose -f compose.yaml -f compose.dev.yaml ps

# confirm the service starts and resolves its own configuration
docker compose -f compose.yaml -f compose.dev.yaml logs <api-service> | head -20
```

`--wait` is the difference between a working one-liner and a flaky one. Without it
the command returns while the database is still initialising, and the first run
fails on a connection error that disappears on the second.

## Configuration

One file, read the same way in every environment, with different values:

```bash
# the example file is the contract: every required key is present, with a
# placeholder value that is safe to commit
cp .env.example .env
# then edit only what must differ locally
```

Rules for the example file, which are correctness rules and not style:

- Every required key is present. A key that only exists in a developer's memory is
  the reason onboarding fails.
- Values are placeholders that cannot work by accident — no real host, no real
  credential, no real domain.
- No line has spaces around `=`, and no line has an inline comment: both are
  mis-parsed by some readers, and the comment becomes part of the value.
- Any value that contains structured data is written so that reading the file with a
  shell does not corrupt it. This is a real trap: a shell performing quote removal
  on a JSON value turns it into something else, and the failure appears in a
  validator several layers away.

## The pre-production check, locally

This is the highest-value local activity, and it is the one that substitutes for a
staging environment:

```bash
# 1. build the image that would actually ship
docker build -t <project>:local .

# 2. run it with production settings
docker compose -f compose.yaml -f compose.prod-local.yaml up -d --wait

# 3. verify, using the gate catalog
curl -fsS http://<host>:<port>/live
curl -fsS http://<host>:<port>/ready
# then: a real authenticated read, a write, and a round-trip through storage

# 4. confirm it is not a development image
docker inspect <container> --format '{{.Config.User}}'      # not root
docker exec <container> <dev-tool> --version                # should not exist
```

Step 4 matters and is skipped. A development image can start perfectly, pass every
functional check, and still be the wrong artifact — carrying a shell, running as
root, or with the source tree mounted. The checks that catch those are cheap and
they cannot be run against a natively-started process.

## Troubleshooting by symptom

| Symptom | Cause | Check |
|---|---|---|
| Fails on the first run, passes on the second | dependencies not ready when the service started | `--wait`; a healthcheck on each dependency |
| Watches fail at startup, after a dependency install | the file watcher is following the dependency directory | scope the watcher to the source directory |
| Fails only on one machine | version mismatch, or an undocumented local setting | compare the resolved versions and the resolved configuration |
| Cannot reach a dependency by name from the service | name resolution differs outside a network | resolve the name from inside the container |
| Reaches the wrong thing on loopback | loopback is the container, not the host | use the container name or the host's address as appropriate |
| Seed fails on a foreign key | seed ordering, or a self-referencing row | load in dependency order; use a staging table for cycles |
| Tests pass alone, fail together | shared state between tests | each test arranges and disposes its own state |

## The inner loop

```bash
# fast: re-run only what changed
<test command> --changed

# the whole tier, before committing
<gate command>
```

The development environment is worth the setup cost only if the fast path is
genuinely fast. If the full check takes minutes, developers batch or skip it, and
the environment stops providing the feedback it was built for. Measure it once; if
the unit tier is slow, that is a defect in the test design, not in the machine.
