# Follow-ups

Recorded here, not done in this change. Grouped by **who can actually fix them**,
because that is the axis a reviewer needs: most of what this change uncovered
cannot be closed by the next person to open this repository.

Each item names what was observed, where it is recorded in more detail, and what
closing it would require. Nothing here is a defect in the local stack, which is
why the gate passes.

---

## A. Owned by this project

### A1. An invalid enum value returns 500, not a validation error

Observed in step 14.8:

```
$ curl -X POST /tickets -d '{"ticket_id":9304, …,"priority":"urgent", …}'
500
sqlalchemy.exc.DataError: (psycopg2.errors.InvalidTextRepresentation)
invalid input value for enum priority_type: "urgent"
```

`priority` and `status` are PostgreSQL enums and nothing validates them before they
reach the database. A client sending a typo gets an opaque 500 naming neither the
field nor the legal values. This is what stopped the gate twice during this
change, and it was the single most expensive defect found.

Closing it means validating against the enum at the request-schema layer, so the
value never reaches the driver. It also means deciding whether the API's
documented error contract for a bad enum becomes 422 — which is a contract
change, and therefore deliberately not smuggled into a change whose stated scope
is the local environment.

The gate now reads the legal labels out of `infra/schema.sql` rather than
hard-coding them, so the fixture cannot drift from the schema again. That removes
the *test's* fragility; it does not fix the API.

### A2. A foreign-key violation returns 500, not a 4xx

Same shape as A1, different cause. `POST /tickets` with a `market_id` or
`equipment_id` that does not exist:

```
sqlalchemy.exc.IntegrityError: (psycopg2.errors.ForeignKeyViolation)
insert or update on table "tickets" violates foreign key constraint "tickets_equipment_id_fkey"
```

A client-supplied id that is not present is client error. It should be a 404 or a
422, not a 500.

### A3. A completed upload leaves a `photos` row with no owner

```
photos.f752bcd9 | Mantenimientos/Correctivos/2026/October/9303/…photo_file.f752bcd9..pdf
                   maintenance_id = NULL
```

`photos.maintenance_id` is `ON DELETE NO ACTION`, so completing an upload against
a maintenance, then deleting that maintenance, leaves the row behind — the delete
either fails or the row is orphaned, depending on the path taken. Step 13.9 found
this: the gate cleaned up its own objects and sessions and still left a row, so
the object was gone while its database record persisted.

The gate sweeps its own residue, matched on its own ticket id and nothing wider —
on a shared core, a blanket `DELETE FROM photos` would destroy another project's
data, and a sweep that ignored its own scoping would be worse than no sweep. That
scoping is deliberate.

Closing it means making the completed upload's row either owned transactionally or
explicitly deletable, so an upload whose parent is gone cleans itself up.

### A4. `TICKET-019` — models are 94 operations stale against the live database

Recorded in `design.md` → Open Questions. Until it is fixed, `alembic
autogenerate` would emit a destructive revision, and **local migrations can never
validate that the models match the schema**. This change therefore takes its local
schema from `infra/schema.sql` plus `alembic upgrade head`, which is correct but
is a workaround: it means the gate proves the *schema* works, not that the
*models* describe it.

`TICKET-018` — 5 tables exist with no model at all — rides along here.

### A5. Stale prose in `README.md` and `docs/development_guide.md`

Both files were edited by this change to describe the local stack, and both still
carry prose that was already wrong before it: absolute paths into a sibling
project's directory, a copy-paste of MinIO's default `minioadmin` credentials
presented as if they were usable, and instructions that only resolve on one
developer's machine. The `minioadmin` reference is now *removed*; the rest
remains. Recorded in the step-16 report's diff analysis and still outstanding.

### A6. `etl/seed_db.sh` is effectively dead in this checkout

`bootstrap.sh` cannot complete — it `cd`s into
`$PROJECT_ROOT/gtk-companies/gtk-base` (`TICKET-016`) — so the ETL path is never
exercised. `etl/seed_db.sh` loads its five tables and *then* prints
`syntax error at or near "SELECT"` from a fidelity check that never runs
correctly. Non-fatal, and the local stack does not depend on it, which is exactly
why it has survived unnoticed. Recorded in `design.md` →
Existing infrastructure.

---

## B. Owned by the project that operates the shared core

Nothing in section B may be fixed from this repository. Editing the core's
declarations from a consumer is the coupling this change exists to remove, and
doing it "just this once" recreates the problem in a new place.

### B1. `docker network connect` attachments do not survive a core recreate

The attachment a consumer makes lives in the container, so the core's next
recreate drops it **silently**: no log line, the API fails on its first request,
and its healthcheck still passes. The idempotent re-run at every bring-up
mitigates this; it does not close the window, which stays open until someone runs
the command.

The durable fix is in the file the core's project owns: each application's network
added to `postgres-gci` and `minio-acme` as `external: true`, so the attachment
is declarative and a recreate reproduces it. That project should also document
that its containers are expected to be multi-homed, and that recreating one drops
every consumer's attachment until its own compose declares it.

Doctrine recorded in `ai-specs/skills/dev-environment-parity/SKILL.md`.

### B2. The core's database and its object store are on different networks

Every consumer must attach to two networks to reach both. An estate-level shared
core should present **one** network to its consumers. Found while executing 5.2.
This is raised against the core's owner, not worked around locally.

### B3. The core's PostgreSQL and MinIO versions cannot be asserted at all

No MinIO version is recorded anywhere in this repository. The gap is real rather
than merely undocumented: the running `minio-acme` image is
`quay.io/minio/minio:latest`, unpinned, so two hosts started at different times do
not agree on what version they are running. Under the shared-core design this
becomes an estate question — the core's parity with the VPS — rather than this
project's.

### B4. Nothing records how the core is backed up

No file in this repository, and nothing reachable from it, records how the core's
PostgreSQL volume or its object store is backed up, how often, where the copies
live, or how a restore is performed *and verified*. That gap is owned wherever
`core/` is owned, and naming an owner from here would be a guess.

Recorded here anyway, for three reasons that make it this change's business:

1. This change makes the core a **hard** dependency of the inner loop, so a lost
   core now stops development, not merely deployment.
2. The app's data lives in that one instance, so a restore is an estate decision
   with this app inside it.
3. Migrations here are not automatically reversible — `docs/learned-lessons.md` §5
   records a schema step that failed quietly enough to look deployed — so recovery
   leans on backup, not on a `downgrade`.

What would make this actionable rather than merely noted: a cadence, an off-host
destination, a restore procedure that is **exercised**, and a check that the copy
is readable. A backup that has never been restored is an assumption.

### B5. This repository holds a forked `core/compose.yml` that has drifted

It has drifted on the service key and on the published port, and no project
records whether that copy is still needed. Either retire the fork here or
reconcile it there — but do **not** resolve it by editing the fork. This change
treats it as no-touch for exactly that reason.

### B6. The core's bring-up should be an estate-level command

This repository's setup command depends on the core being startable from the
project that owns it. If that project moves, or its path is not stable, setup
breaks. This change removes the *assumption* that the core is up; it does not
remove the coupling.

---

## C. Deployment-contract changes that are deliberately out of scope

### C1. Renaming the deployed network needs its own change

`infra/vps/docker-compose.yml` is no-touch here because it is the deployed
contract, and renaming its network changes that contract. It needs its own
change, because renaming one line leaves the deployment procedure wrong in six
places operators actually run:

| Artifact | What still says `infra-net` |
| --- | --- |
| `infra/vps/docker-compose.yml` | the network key on `caddy`, `api-acme`, `migrate`, and the `networks:` block itself |
| `docs/deployment-guide.md` | `docker network create`, `connect`, `inspect`, subnet discovery, estate listing |
| `infra/vps/Caddyfile` | the comment recording that both site blocks resolve by container name on the shared network |
| `ai-specs/skills/deploying-backend-vps/SKILL.md` | `networks: [infra-net]` in the documented deploy |
| `README.md` | the published `docker network connect infra-net minio-acme` |
| `tests/test_deploy_assets.py` | the assertion that `migrate` joins `infra-net` |

It also needs a **live** step, which no file edit performs: create
`my-tickets-network` on the VPS, attach both core containers, then re-verify
media loads. The documented failure for a MinIO not attached to the API's network
is a DNS error surfacing as media 404s, so the check is a functional media fetch,
not a healthcheck.

### C2. No application has network redundancy

Each application's network is a single bridge with no second path and no failover,
and there is no second attachment of the core to anything.

The useful part is not the gap but that the remedy is nearly free **because** of
the pattern this change adopted: an application owns its network, so a second
network is added on the application side and the core is connected to both — the
core changes nothing. Under the arrangement this change rejected, redundancy would
have required a coordinated change across the core and every consumer, which is
precisely the coupling being removed.

Residual risk, stated plainly: because an attachment dies with its container, a
recreate silently drops it, so any second path needs a check that **both**
attachments are present, not an assumption that they are. Not implemented — it
needs its own decision about what fails over and to where.

### C3. Building on the target host is a separate change

Recorded as decision 12 (`design.md`): no cross-host image build.

### C4. Local provisioning: self-service or owner-run?

This change lets a developer create their own role, database and bucket from this
repository's setup command, because that is additive and confined to this project.
The stricter option is that the core's owner runs provisioning and this project
only connects.

The trade is onboarding speed against who is authorised to add state to a shared
instance. It is a question about the estate, not about this repository — and it
also decides whether the connection-level isolation used on the VPS should ever be
applied locally, which would require editing a shared configuration file and
restarting a shared container.

### C5. Shared declarations get copied and then drift

Shared declarations are copied into consuming repositories, where they drift
while the shared containers keep running. `ai-specs/skills/dev-environment-parity/SKILL.md`
now states the procedure and `ai-specs/harness-ia.md` records why — but no skill
can prevent a consumer from editing a declaration it does not own. That needs the
estate to say which project owns each shared declaration.

---

## D. The mistake this change nearly made, recorded because it is a class

A find-and-replace of the network name across `infra/vps/docker-compose.yml`
renamed the `name:` value but left the network **key** and all five internal
references as `infra-net`. Compose resolves services through the key, so the file
stayed self-consistent enough to validate while placing `caddy`, `api-acme` and
`migrate` on **another tenant's bridge** — a change to a public TLS entrypoint and
the media origin, produced by a rename that looked complete.

Three lessons, all three carried by this change:

1. A network rename is a coordinated change across the compose key, the declared
   name, every service reference, and every document that names it — or it is not
   a rename.
2. A value that silently changes routing must never be changed by a tool that
   reports success.
3. The file's own comment at `infra/vps/docker-compose.yml:113` already warned
   that `my-dopamine-network` is also `provider-frontend`'s bridge. The warning
   existed and was not read. A guard that greps for foreign tenant names in
   committed deployment files is worth having estate-wide.
## E. Decisions this change takes, rather than leaving to chance

Two tasks in `tasks.md` asked for a decision and were at risk of being settled by
accident. Both are now decided explicitly, in one direction, with the reasoning
recorded so a later reader can reverse them deliberately.

### E1. Local stops at reference data — no demo operational records

`tasks.md` §8.17 asked whether the local environment should carry a synthetic
ticket set so costs can be demonstrated end to end. **`materials`, `services` and
`preliquidated` cannot load without `tickets` and `maintenances`**, which
`etl/seed_db.sh` classifies as business data — line items on a live record.

**Decision: local stops at reference data.** `infra/local/seed/` holds `uom`,
`fsm_users`, `equipments`, `markets` and `technicians`, and no operational rows.
The gate creates its ticket and maintenance at run time through the API and
deletes them, which demonstrates the full ticket lifecycle *and* leaves nothing
behind — a behaviour a committed seed file could not have.

What must not happen, per §8.17, is this answer arriving by someone dropping a
`tickets.csv` into `infra/local/data/` and finding that `--allow-business-data`
happily loads it. That hazard is closed structurally rather than by convention:

- The seed data folder is git-ignored.
- `setup.sh` copies only the CSVs it just committed into that folder, and reads
  only those. It never reads a CSV it did not just place there itself.

So a stray CSV is not merely unlisted — it is never opened. The consequence to
state plainly: a local environment cannot show a ticket with costs attached
without this decision being revisited, and whoever revisits it must add the rows
through a path that keeps that guarantee.

### E2. Uploaded objects remain non-garbage-collectable by the application

`tasks.md` §10.16 asked whether to add a deletion route or accept that
`POST /uploads/complete` creates an object nothing removes.
`app/api/routes/uploads.py` exposes `init`, `chunk`, `status` and `complete`, and
nothing else.

**Decision: accept for this change, and record the gap.** The gate hides the gap
by removing its own object with the object-store client — a capability the
application itself does not have — so an abandoned upload session leaves an object
in the bucket forever. Fixing it means adding `DELETE /uploads/{upload_id}` scoped
to the session's owner, which is application work that changes the API surface,
and therefore outside a change that states it alters no endpoint.

Two things make the deferral safe rather than merely convenient: the gate's own
cleanup is verified (16.6: 0 objects), and this is a storage-cost and tidiness
problem, not a correctness one. It becomes urgent the moment local environments
are created per developer and left running.

Related, and separately tracked as A3: even with such a route, a completed upload
whose parent is deleted still leaves a `photos` row behind, because
`maintenance_id` is `ON DELETE NO ACTION`.

---

