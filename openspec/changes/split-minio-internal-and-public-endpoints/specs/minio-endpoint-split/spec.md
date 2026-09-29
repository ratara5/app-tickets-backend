## ADDED Requirements

### Requirement: Separate internal dial target from public signing origin
`app/core/settings.py` SHALL read two independent origins. `MINIO_ENDPOINT` (with
`MINIO_PORT` and `MINIO_SECURE`) SHALL be the address the backend process itself uses to reach
the object store. `MINIO_PUBLIC_ENDPOINT` (with optional `MINIO_PUBLIC_PORT` and
`MINIO_PUBLIC_SECURE`) SHALL be the origin embedded in presigned URLs. When
`MINIO_PUBLIC_ENDPOINT` is unset the system SHALL fall back to `MINIO_ENDPOINT`, so a
configuration that sets only the pre-existing variables behaves exactly as it did before.
`MINIO_ENDPOINT` SHALL be documented and configured as an internal name (`127.0.0.1` when the
backend runs on the host, the container name when it runs in Docker) and SHALL NOT be a LAN
address.

#### Scenario: Presigned URL is signed with the public origin
- **WHEN** the backend generates a presigned URL and `MINIO_PUBLIC_ENDPOINT` is set
- **THEN** the returned URL's scheme, host and port come from `MINIO_PUBLIC_ENDPOINT` (or `MINIO_PUBLIC_PORT` / `MINIO_PUBLIC_SECURE` when set)
- **AND** the internal dial target is not present in the URL

#### Scenario: Public origin unset falls back to the internal endpoint
- **WHEN** `MINIO_PUBLIC_ENDPOINT` is unset
- **THEN** presigned URLs are signed with `MINIO_ENDPOINT`, `MINIO_PORT` and `MINIO_SECURE`
- **AND** no configuration error is raised

#### Scenario: Internal traffic does not depend on the public origin
- **WHEN** the backend uploads an object while `MINIO_PUBLIC_ENDPOINT` is unreachable from the backend host
- **THEN** the upload succeeds because it is dialed against `MINIO_ENDPOINT`

#### Scenario: Public port and scheme differ from the internal ones
- **WHEN** `MINIO_PUBLIC_ENDPOINT=media.example.com`, `MINIO_PUBLIC_PORT=443` and `MINIO_PUBLIC_SECURE=true` while `MINIO_ENDPOINT=minio-acme` and `MINIO_PORT=9000`
- **THEN** presigned URLs use `https` on port `443` at `media.example.com`
- **AND** uploads are dialed at `minio-acme:9000` over plain HTTP

### Requirement: Presigning is local and performs no network I/O
`get_presigned_url()` SHALL sign with a client constructed from the public origin with an
explicit `MINIO_REGION` (default `us-east-1`). Because minio-py resolves the SigV4 region from
the client when one is supplied, presigning SHALL NOT issue `GetBucketLocation` or any other
request. The same explicit region SHALL be set on the internal client.

#### Scenario: Presign succeeds with no network access
- **WHEN** the internal endpoint is unreachable and `get_presigned_url()` is called
- **THEN** a presigned URL is returned, whose host equals `MINIO_PUBLIC_ENDPOINT`
- **AND** no HTTP request is issued by the presign path

#### Scenario: No GetBucketLocation call during presigning
- **WHEN** the MinIO HTTP client is replaced by a stub that records every request
- **THEN** `get_presigned_url()` issues no request, and in particular no `GET /{bucket}?location=`

### Requirement: Presigned URLs are never rewritten
The system SHALL NOT post-process, string-replace, re-host or otherwise mutate a presigned URL
after signing. The `Host` header is covered by the SigV4 signature, so any mutation produces
`403 SignatureDoesNotMatch`. Changing the public origin SHALL take effect by changing
configuration and restarting, never by transforming an already issued URL.

#### Scenario: Configured public origin is the only thing that decides the host
- **WHEN** `MINIO_PUBLIC_ENDPOINT` changes and the backend restarts
- **THEN** newly issued presigned URLs carry the new host
- **AND** no code path substitutes, prefixes or strips a host in an issued URL

### Requirement: Fail fast when the object store is unreachable
The bucket SHALL be ensured once at startup and the result memoized, instead of on every
upload. If the store cannot be reached, the backend SHALL abort startup with a single error
that names the configured internal endpoint, port and scheme. An unreachable store SHALL NOT
surface as a per-request urllib3 retry traceback.

#### Scenario: Unreachable store aborts startup once
- **WHEN** the startup probe runs against an endpoint that returns `EHOSTUNREACH`
- **THEN** exactly one probe is attempted
- **AND** a `StorageUnavailableError` is raised whose message names the configured endpoint
- **AND** the message states which service to start and which setting to change

#### Scenario: Bucket is not probed on every upload
- **WHEN** several uploads are performed against a reachable store
- **THEN** `bucket_exists` is not called once per upload
- **AND** the uploads proceed normally

#### Scenario: Store recovers after a failed probe
- **WHEN** a probe failed at startup and the store becomes reachable
- **THEN** the next upload succeeds without restarting the backend
- **AND** no stale failure is served from the memoized result

### Requirement: Transport errors become domain errors
Connection-level failures SHALL be translated into `StorageUnavailableError` at the storage
boundary, so that callers and logs never expose a urllib3 retry traceback or an internal
address. The original exception SHALL be logged once.

#### Scenario: No route to host is translated
- **WHEN** a MinIO call raises `EHOSTUNREACH` (errno 113)
- **THEN** a `StorageUnavailableError` is raised naming the configured endpoint
- **AND** no `NewConnectionError` reaches the caller

#### Scenario: Connection refused is translated
- **WHEN** a MinIO call raises `ECONNREFUSED` (errno 111)
- **THEN** a `StorageUnavailableError` is raised naming the configured endpoint

#### Scenario: Credentials and bucket errors are not masked
- **WHEN** MinIO returns an `S3Error` such as `AccessDenied` or `NoSuchBucket`
- **THEN** the error propagates unchanged, because it is not a reachability problem
