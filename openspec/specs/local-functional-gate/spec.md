# local-functional-gate Specification

## Purpose
What a developer can prove about the built image before release, by running it locally against the shared core as an isolated consumer. The gate exercises authentication, write, maintenance, a full object-storage round trip and delete through the application's own clients, and states plainly which of its results do not transfer to the deployed environment.
## Requirements
### Requirement: The gate writes only to this project's own database and bucket, and refuses to run otherwise

Because the gate mutates the shared core that other applications use, it SHALL verify, before
it performs any write, that the resolved connection names this project's own database and
that the object-store bucket is this project's own. If either does not, the gate SHALL abort
without writing anything and SHALL report which object it resolved and which it expected.
This precondition is not advisory: it is the check that prevents a verification step from
becoming a cross-tenant write.

#### Scenario: The gate aborts against another project's database

- **WHEN** the gate resolves a database name that is not this project's own
- **THEN** it performs no write and exits non-zero
- **AND** it reports the resolved database name and the expected one

#### Scenario: The gate aborts against another project's bucket

- **WHEN** the gate resolves a bucket that is not this project's own
- **THEN** it uploads nothing and exits non-zero
- **AND** it reports the resolved bucket and the expected one

#### Scenario: The precondition is checked before the first mutation

- **WHEN** the gate begins
- **THEN** the own-database and own-bucket assertions complete before any insert, update or upload is issued
- **AND** a failure in the precondition leaves the database and the bucket as they were found

#### Scenario: The expected names come from one place

- **WHEN** the expected database, role and bucket names are compared
- **THEN** the gate compares against the same identifiers the bring-up provisioned
- **AND** no name is hardcoded separately in the gate

### Requirement: The functional gate proves the built image works

The repository SHALL provide a single verification command whose output is a fixed block
suitable for pasting into a release note. The gate SHALL verify the built image rather than
a development image, SHALL exercise an authenticated read, a write, and a round trip
through the application's own object-store client, and SHALL exit non-zero on the first
failure.

#### Scenario: One command brings the stack up and a second proves it works

- **WHEN** a developer starts from a clean checkout
- **THEN** one documented command brings the stack up
- **AND** a second documented command proves it works, with no undocumented step between them

#### Scenario: The gate runs against the built image

- **WHEN** the gate inspects the running application container
- **THEN** it asserts the container's configured user is not root and that the image contains no development tooling
- **AND** these assertions are made against a container, so they cannot be satisfied by a natively started process

#### Scenario: The gate exercises a real authenticated read

- **WHEN** the gate obtains a token by authenticating against the running API
- **THEN** it performs an authenticated read of the authenticated user's own record
- **AND** the read is served by the running image, not by a test double

#### Scenario: The gate exercises a write

- **WHEN** the gate performs a write through the running API
- **THEN** the write is accepted and persisted
- **AND** the write lands in this project's own database, which the precondition has already established
- **AND** the gate removes or reverts what it created, leaving the database as it found it

#### Scenario: The gate round-trips through the application's own storage client

- **WHEN** the gate uploads an object through the application's upload path, presigns a read, fetches it back and compares bytes
- **THEN** the round trip completes through the application's own client, so an exhausted connection pool, a missing migration, or wrong credentials fail the gate
- **AND** the gate asserts the signed URL's host is the configured public origin, not the internal dial target

#### Scenario: The gate output is pasteable and the gate fails loudly

- **WHEN** the gate succeeds
- **THEN** it prints a fixed block naming the built image, the resolved origins, and the result of each check
- **AND** when any check fails it stops at the first failure and exits non-zero

### Requirement: The limits of local verification are stated

The repository SHALL state that a passing local gate does not replace a staging
environment, and SHALL enumerate the VPS-specific behaviours the local gate does not
exercise.

#### Scenario: Documentation states what a local gate cannot cover

- **WHEN** the gate documentation is read
- **THEN** it states that the local check does not replace a staging environment
- **AND** it states that the VPS's own network, its TLS origin, and its scheduling are not exercised locally
- **AND** it names the VPS gates that cover those behaviours
- **AND** it states that because local and deployment now reach a shared core the same way, a passing gate is greater evidence of configuration correctness and is not greater evidence of deployment correctness

#### Scenario: Consuming a shared core does not verify the core's own configuration

- **WHEN** the gate passes against the shared core
- **THEN** the documentation states that the gate exercises this project's access to the core, not the core's own health, backup, patching or availability
- **AND** it states that a defect in the core's declaration remains visible locally as a connection failure and is owned by the project that operates it

#### Scenario: No staging environment is introduced as a dependency

- **WHEN** the implementation plan is read
- **THEN** no staging environment, orchestrator, deployment pipeline, or observability vendor is required
- **AND** the substitute for staging is running the built image locally with production settings

### Requirement: Building the image on the target is out of scope and recorded as a dependency

The repository SHALL NOT require the image to be built on the deployment target as part of
this change. Producing an image artifact on one host and running it on another SHALL be
recorded as a dependency of a separate change.

#### Scenario: The local gate builds and runs on the same host

- **WHEN** the functional gate runs
- **THEN** the image is built on the developer's machine and run on that same machine
- **AND** no image is built on the VPS as part of this change

#### Scenario: The cross-host artifact question is recorded, not answered here

- **WHEN** the design is read
- **THEN** building on the target host and transferring the resulting artifact is named as a separate change with its own decision