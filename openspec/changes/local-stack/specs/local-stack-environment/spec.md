## ADDED Requirements

### Requirement: Local topology runs the application natively and consumes the shared core

The repository SHALL provide a local stack definition at `infra/local/docker-compose.yml`
that declares only this application's own services — the API and the `migrate` job — and
SHALL consume PostgreSQL and MinIO from the shared core that other projects in this estate
already use, both on the developer machine and on the VPS. The local definition SHALL NOT
declare a PostgreSQL service, an object-store service, a data volume, or a custom
database or object-store image. The API service and its test suite SHALL run natively from
the project virtualenv. All local definitions SHALL exist only under `infra/local/`; the
root `docker-compose.yml`, every file under `infra/vps/`, and every declaration owned by the
project that operates the core SHALL remain unmodified.

#### Scenario: One command reaches a working environment

- **WHEN** a developer runs the documented bring-up command from a clean checkout
- **THEN** PostgreSQL and MinIO are reachable from the host on the shared core
- **AND** this project's own role, database and bucket exist on that core
- **AND** the command reports the resolved host and port of each dependency before it returns

#### Scenario: A missing prerequisite is named rather than reported as a connection error

- **WHEN** the bring-up command runs and the shared core is not available
- **THEN** the command fails with a message naming the dependency that is absent and the project that owns it
- **AND** no application process is started and no partial provisioning is left behind

#### Scenario: The API runs natively for the inner loop

- **WHEN** the developer starts the API from the virtualenv
- **THEN** the process reads its configuration through `app/core/settings.py` from the developer's `.env`
- **AND** no API container is required for editing-and-reload work

#### Scenario: The built image is exercised before release

- **WHEN** the developer runs the pre-release command
- **THEN** the image produced by `Dockerfile`'s default `runtime` stage is started locally with production-shaped settings
- **AND** the resulting container is the artifact the functional gate inspects

#### Scenario: Shared VPS assets are untouched

- **WHEN** the local bring-up command runs
- **THEN** no file under `infra/vps/` is read for configuration, modified, or executed
- **AND** no file in the core project's own declaration is modified or executed for configuration

#### Scenario: The local definition declares no competing copy of a shared dependency

- **WHEN** the local compose file is read
- **THEN** it declares no PostgreSQL service, no object-store service, no data volume and no build or image key for either
- **AND** every dependency it reaches is reached across the single network the local stack declares for itself

### Requirement: Local and VPS ports and hostnames are recorded separately, never silently aligned

The repository SHALL document the local and VPS port and hostname values side by side, and
SHALL NOT change a VPS value to match a local one. Because this project publishes no
dependency, the documented local dependency values SHALL be the values the shared core
already publishes, and each SHALL record the declaration it was read from. The local stack
SHALL publish only its own API, on `127.0.0.1`.

#### Scenario: Local values differ from VPS values and both are documented

- **WHEN** a reader compares the documented tables
- **THEN** each dependency shows its local value and its VPS value in the same row
- **AND** no local value is presented as the VPS value

#### Scenario: In container run mode the local dependency values equal the VPS values

- **WHEN** the table records the host and port each dependency is reached on inside a container
- **THEN** the local entry and the VPS entry are the same host name and the same port for both dependencies

#### Scenario: Only the API is published locally

- **WHEN** the local stack starts
- **THEN** the only published port is the API's, bound as `127.0.0.1:<port>:<container-port>` and not as `0.0.0.0`
- **AND** the bring-up command prints the bound address

#### Scenario: A dependency value copied from the core records its provenance

- **WHEN** a host, port or network name in the local configuration was copied from the core's declaration
- **THEN** the value is accompanied by the declaration it was read from
- **AND** no copied value is presented as a local choice

### Requirement: The local stack consumes shared state as an isolated consumer and never provides a competing copy

The local stack SHALL reach PostgreSQL and MinIO across a single network of its own, which it
SHALL create and SHALL NOT share with another project. It SHALL connect the shared core's
already-running containers to that network, and SHALL NOT stop, restart, recreate or remove
them in order to do so. Isolation from the other consumers of that core SHALL be achieved by
this project's own database, its own least-privilege role, its own bucket and its own
credentials, never by a private instance. The local stack SHALL NOT declare its own copy of a
dependency that the core already provides, SHALL NOT mount a shared data volume, SHALL NOT
reuse a shared container name, and SHALL NOT edit any shared configuration file in order to
reach a shared dependency.

#### Scenario: One local network carries both dependencies

- **WHEN** the local compose file declares its network
- **THEN** it declares exactly one network, owned by this project, which both local services attach to
- **AND** it names no network belonging to another project or to the core's own declaration
- **AND** the network is created only after the core's containers are confirmed running

#### Scenario: The core's containers are connected, not replaced

- **WHEN** the bring-up command reaches the core's containers
- **THEN** it attaches each already-running container to the local network and does nothing else to it
- **AND** it issues no stop, restart, remove or start against a container it did not create
- **AND** the connection is idempotent, so a second run attaches nothing and changes nothing

#### Scenario: Attachments lost to container recreation are re-established

- **WHEN** the core's container was recreated since the last bring-up, so it no longer carries the local network
- **THEN** the bring-up command re-attaches it and reports that it did so
- **AND** a second bring-up reports the attachment already present

#### Scenario: Teardown releases the network it borrowed

- **WHEN** the teardown command runs
- **THEN** it detaches the core's containers from the local network before the local project is removed
- **AND** the network is removed rather than left behind holding an attachment to a container this project does not own

#### Scenario: A local cleanup cannot remove a shared container

- **WHEN** the documented local teardown command runs
- **THEN** it removes only containers carrying the local compose project label
- **AND** no container belonging to the core's compose project is stopped, removed or reconfigured

#### Scenario: Isolation comes from this project's own objects

- **WHEN** the local configuration is resolved
- **THEN** the database name, role name, bucket name and credentials are this project's own
- **AND** no name or credential belonging to another project on the same core appears in any local file

#### Scenario: Reaching a shared dependency never requires editing a shared file

- **WHEN** the local environment needs a capability that the core's existing configuration does not provide
- **THEN** the requirement is recorded as a follow-up against the project that owns the core's declaration
- **AND** no shared configuration file is edited and no shared container is restarted as part of this change

#### Scenario: The shared declarations this project inherited are not edited

- **WHEN** a defect is observed in a shared dependency's declaration, including the copy of it under `core/`
- **THEN** `core/compose.yml` is left unmodified by this change
- **AND** the defect is recorded as a follow-up against the project that owns the declaration, identified by the compose project that created the running container

#### Scenario: Local provisioning is additive and confined to this project

- **WHEN** the bring-up command provisions this project on the shared core
- **THEN** it creates only objects named for this project — a role, a database, a bucket, a user and credentials
- **AND** it drops no existing object, and changes no existing object's grants, ownership or configuration

### Requirement: Configuration is resolved by one code path with no undecided defaults

`app/core/settings.py` SHALL be the single configuration resolution path for every process
in every environment: the API, the Alembic migrations, and the test suite. Every setting
whose value can differ between environments SHALL be required, with no default, so an
omitted value fails loudly instead of resolving to a value no one chose.

#### Scenario: An omitted environment-varying setting aborts the process

- **WHEN** a required setting that differs per environment is absent from the environment and from the env file
- **THEN** importing `app.core.settings` raises a validation error naming the missing setting
- **AND** no process starts with a substituted value

#### Scenario: The public MinIO origin no longer falls back to the internal one

- **WHEN** the internal and public object-store origins are resolved
- **THEN** each public component is required and is never derived from its internal counterpart
- **AND** a configuration that omits a public component fails rather than signing URLs with the internal host

#### Scenario: Constants that are genuinely invariant keep their single definition

- **WHEN** a setting has one correct value in every environment
- **THEN** it MAY remain a default, and that default SHALL be documented as invariant

#### Scenario: One env file name, different values per environment

- **WHEN** the local and VPS environments are configured
- **THEN** both use the same env file name and the same key names
- **AND** the difference between the environments is expressed only in values and in the comments describing them

### Requirement: Name resolution is explicit per run mode and loopback is never inherited

The local configuration SHALL state, per run mode, the exact hostname used to reach
PostgreSQL and MinIO, and SHALL document that a loopback address inside a container
resolves to that container rather than to the host. The two run modes SHALL differ in the
same way the deployed environment's two access paths differ, and each SHALL be recorded
against the value the deployed environment uses for the same access path.

#### Scenario: Native run mode reaches dependencies through the core's published host port

- **WHEN** the API runs natively and reaches PostgreSQL
- **THEN** the configured host is the loopback address and the port is the port the core publishes for host-side callers, not the in-container port
- **AND** the same rule holds for the object store

#### Scenario: Container run mode reaches dependencies by the core's container name

- **WHEN** the built image runs as a container on the local network
- **THEN** the configured host is the core's own container name for each dependency
- **AND** the configured port is the in-container port
- **AND** these values are identical to the values the VPS deployment uses for the same access path
- **AND** no inherited loopback value from the native configuration is left in effect

#### Scenario: The loopback trap is stated where a run mode is configured

- **WHEN** a run mode overrides a hostname that differs between host and container execution
- **THEN** the override carries a comment stating that `127.0.0.1` inside a container is the container itself

### Requirement: The shared object store's published ports and this project's signing origin are recorded, not owned

This project SHALL NOT own the object store's host ports. The local environment SHALL use the
shared core's published ports, SHALL record no local public TLS origin exists, and SHALL
record the VPS value the local signing origin corresponds to. Because several applications
share one object store, the signing origin SHALL be recorded as a per-application setting
rather than a property of the object store.

#### Scenario: Local object store has no public signing origin of its own

- **WHEN** the local configuration sets the object-store public signing origin
- **THEN** it points at the loopback address and plain HTTP on the core's published API port, because no local TLS origin terminates traffic
- **AND** the VPS value for the same setting is documented alongside it as the domain, port `443`, and TLS

#### Scenario: Each application signs for its own origin on the shared object store

- **WHEN** two applications share the same object store
- **THEN** each signs its URLs with the public origin configured for that application
- **AND** neither application changes a setting that belongs to the object store or to another application

#### Scenario: A presigned URL produced locally is fetchable from the host

- **WHEN** the local stack signs a URL with the public origin and the developer fetches it from the host
- **THEN** the request succeeds against the shared object store
- **AND** the fetch exercises the application's own client rather than a raw connection

### Requirement: Caddy is excluded locally and its responsibilities are verified another way

The local stack SHALL NOT run Caddy. Because Caddy exists only to terminate TLS for a
public origin that does not exist locally, the repository SHALL specify which checks
replace it, and SHALL state explicitly which of Caddy's responsibilities remain
unverified locally. If the shared core is later found to own a TLS edge that consumers join,
that arrangement SHALL be evaluated as a consumer arrangement under the same rules as any
other shared dependency rather than adopted by reference.

#### Scenario: The local stack declares no TLS edge

- **WHEN** the local compose file is read
- **THEN** it declares no Caddy service and mounts no Caddyfile
- **AND** the API is reachable on its loopback host port directly

#### Scenario: Media path verification replaces the local TLS edge

- **WHEN** the functional gate runs
- **THEN** it performs an object write, a presigned read back, a byte comparison and a delete through the application's own storage client
- **AND** it asserts the signed URL's host is the configured public origin

#### Scenario: Unverified responsibilities are stated

- **WHEN** the local verification documentation is read
- **THEN** it states that TLS termination, the public DNS name, and edge proxying are not exercised locally
- **AND** it names the VPS gate that covers them

### Requirement: Hot reload watches application source only

The documented reload command SHALL restrict the file watcher to application source
directories and SHALL exclude the dependency directory, the cache directory and any build
output, so that installing a dependency cannot exhaust the operating system's watch limit.

#### Scenario: The reload command carries an explicit watch scope

- **WHEN** the developer starts the API with reload enabled
- **THEN** the command restricts watching to the application source directory rather than the project root

#### Scenario: A dependency install does not consume watch descriptors

- **WHEN** the developer installs or updates dependencies in the project virtualenv
- **THEN** the reload process's watch descriptor count does not scale with the number of installed packages
- **AND** the reload process does not fail with a watch-limit error afterwards
