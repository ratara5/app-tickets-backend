# local-data-provisioning Specification

## Purpose
This project creates its own role, database, bucket and credentials on the shared core, and applies the schema of record plus a deterministic local seed. Provisioning is additive and confined to this project: it drops nothing, widens no privilege beyond the canonical least-privilege template, and commits no credential.
## Requirements
### Requirement: This project's role, database and bucket are created on the shared core, additively

The local bring-up SHALL provision this project on the shared core by creating only objects
named for this project: a least-privilege runtime role, a database, an object-store bucket,
an object-store user and this project's own credentials. Provisioning SHALL NOT drop or
alter any object it did not create, SHALL NOT change another project's grants, ownership or
configuration, and SHALL NOT edit any shared configuration file or restart any shared
container in order to succeed. Every provisioning statement SHALL be idempotent, so a second
run against an already-provisioned core changes nothing.

#### Scenario: A clean checkout provisions itself on the shared core

- **WHEN** the bring-up command runs against a core that is up but has no objects for this project
- **THEN** this project's role, database, bucket, user and credentials exist
- **AND** no other object on the core is created, altered or removed

#### Scenario: A second run is a no-op

- **WHEN** the bring-up command runs again against the same core
- **THEN** it completes without error and reports that the objects already existed
- **AND** no object's grants, ownership or configuration differ from before the run

#### Scenario: Provisioning never reaches the shared configuration

- **WHEN** the bring-up command runs
- **THEN** no shared configuration file, including `pg_hba.conf`, is opened for writing
- **AND** no container belonging to the core's compose project is stopped, restarted or recreated

#### Scenario: A capability the core lacks is reported, not configured around

- **WHEN** provisioning requires a capability the core's current configuration does not provide
- **THEN** the bring-up command fails with a message naming the capability and the project that owns the core's declaration
- **AND** it does not modify the core's declaration to supply the capability itself

#### Scenario: Provisioned objects are the project's, not the change's

- **WHEN** the change that created them is reverted
- **THEN** the role, database, bucket, user and credentials remain in place
- **AND** no rollback step removes them, because removal is a separate explicit act scoped by name to this project's objects

### Requirement: Deterministic local seeding without production data or committed credentials

The repository SHALL provide a local seed that creates only the reference and master data
the application requires to start and to serve a first request. The seed SHALL target this
project's own database and its own bucket on the shared core, SHALL be deterministic,
re-runnable, and free of production data in every form, including anonymized extracts. It
SHALL load through the same guarded loader the repository already uses, rather than through
a second, weaker mechanism. No credential SHALL appear in any committed file; the seed
user's password SHALL be read from the developer's git-ignored env file and SHALL have no
committed default.

#### Scenario: A clean database becomes usable without manual data work

- **WHEN** the bring-up command runs against a core with no objects for this project
- **THEN** the schema is applied, migrations are brought to head, and the seed has run
- **AND** an authenticated read and a write both succeed with no further manual steps

#### Scenario: The seed is idempotent

- **WHEN** the seed runs a second time against the same database
- **THEN** it completes without error and leaves the same rows
- **AND** it does not duplicate rows that carry a natural key

#### Scenario: No production data is committed

- **WHEN** the committed seed is inspected
- **THEN** every row is structurally faithful to the schema but carries synthetic values
- **AND** no row is a copy, an extract, or an anonymized form of a production row

#### Scenario: No credential is committed

- **WHEN** the committed files are searched
- **THEN** no database password, object-store secret, or signing key literal is present
- **AND** the seed user password is read from the git-ignored env file, with the committed example carrying a generation instruction instead of a value

#### Scenario: The local role is least-privilege, as on the VPS

- **WHEN** this project's role is provisioned on the shared core
- **THEN** the runtime role is created from the shared provisioning script with substituted placeholders
- **AND** the runtime role owns nothing and holds no schema-modification privilege
- **AND** the role holds no privilege on another project's database on the same core

#### Scenario: No credential or object name belonging to another project is used

- **WHEN** the local environment is inspected
- **THEN** no database, role, bucket or user belonging to another project on the shared core is named
- **AND** no credential from another project's environment file appears

### Requirement: The local schema is the shared schema of record, not generated from models

The local bring-up SHALL create the schema from `infra/schema.sql`, the same file
`docs/deployment-guide.md` §2.2 applies on the VPS, and SHALL NOT generate a schema from
the SQLAlchemy models. The reason SHALL be recorded where the local bring-up defines the
step.

#### Scenario: Schema creation uses the committed dump

- **WHEN** the local bring-up applies the schema
- **THEN** it applies `infra/schema.sql` with error-stopping enabled
- **AND** a post-condition verifies a table the application requires at request time is present before proceeding

#### Scenario: Models are never used as the schema source

- **WHEN** the bring-up reaches the schema step
- **THEN** no autogenerate or metadata-create path is invoked to build the schema
- **AND** the recorded reason states that the models are stale against the live database and would load a wrong schema silently

### Requirement: Local migrations reuse the same image stage as the VPS

The local bring-up SHALL bring the database to the Alembic head using the `migrate` target
of the same `Dockerfile` the VPS migration job builds, and SHALL pass the schema-owning
credentials explicitly rather than relying on defaults.

#### Scenario: The migration runs in the shared migrate image

- **WHEN** the local bring-up runs the migration step
- **THEN** it invokes the `migrate` build target of `Dockerfile`, the same target `infra/vps/docker-compose.yml` declares
- **AND** the elevated credential is passed explicitly, never read from a default

#### Scenario: The local database reaches the head revision

- **WHEN** the migration step completes
- **THEN** the recorded revision equals the repository's single head revision
- **AND** the step verifies the revision before proceeding, and fails loudly if more than one head exists

### Requirement: The PostgreSQL image comes from the shared core and this project builds none

This project SHALL NOT declare, build or pin a PostgreSQL image. The extension that
`infra/schema.sql` requires SHALL be satisfied by the image the shared core already runs.
Where the core's image does not provide a required capability, that SHALL be recorded as a
finding against the core's declaration rather than worked around with a local image.

#### Scenario: The extension is available at schema-load time

- **WHEN** the schema is applied to this project's database on the shared core
- **THEN** the `CREATE EXTENSION IF NOT EXISTS pg_uuidv7` statement in `infra/schema.sql` succeeds
- **AND** no local image was built to make it succeed

#### Scenario: A missing capability in the core's image is a finding, not a workaround

- **WHEN** the shared core's PostgreSQL image lacks a capability `infra/schema.sql` requires
- **THEN** the bring-up command fails with a message naming the missing capability and the project that owns the core's image
- **AND** this project does not build a substitute image to satisfy its own bring-up

#### Scenario: Version drift from the VPS is recorded

- **WHEN** the local and VPS PostgreSQL versions are documented
- **THEN** both versions appear in the same table, with the local column identifying the core as the source
- **AND** any difference, including a version that is recorded nowhere, is stated rather than implied to be equivalent

### Requirement: Bring-up starts the shared core only through its owner's documented mechanism

The local bring-up SHALL obtain a running shared core by invoking the mechanism the core's
owning project documents, and SHALL NOT recreate, reconfigure, recreate-from-image or
otherwise mutate any container it does not own. Starting a container that is already running
SHALL be a no-op rather than a restart, because a restart interrupts every other consumer of
that instance.

#### Scenario: Bring-up creates only its own containers

- **WHEN** the local bring-up runs
- **THEN** it creates containers declared in the local compose file only
- **AND** it issues no create, remove, or reconfigure command against a container owned by another project

#### Scenario: Starting the core does not restart a running core

- **WHEN** the local bring-up runs and the core's containers are already running
- **THEN** it leaves them running and does not restart them
- **AND** it proceeds once the dependencies answer, rather than waiting for a start event

#### Scenario: The core's availability is checked, not assumed

- **WHEN** the local bring-up runs and the core's containers exist but are stopped
- **THEN** the bring-up starts them through the owner's documented command
- **AND** if that mechanism is unavailable, the bring-up fails naming the dependency and its owner instead of waiting or hanging

#### Scenario: Local teardown is scoped to the local project

- **WHEN** the documented teardown command runs
- **THEN** it stops only the local compose project's containers
- **AND** its documented output names the containers it stopped
- **AND** no container belonging to the core's compose project is stopped