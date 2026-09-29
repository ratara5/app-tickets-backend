## Context

A photo upload outage traced to `192.168.10.26:9000` returning `EHOSTUNREACH`. `.26` is a
DHCP lease on `wlp2s0`; the machine is now `192.168.10.30`. `minio-acme` is healthy and
publishes `0.0.0.0:9000-9001`, reachable on the current IP from the host and from containers.

Two facts drive the design, both verified against the installed `minio-py 7.2.7`
(`venv/lib/python3.12/site-packages/minio/api.py`):

1. **The `Host` header is signed.** `presigned_get_object` → `get_presigned_url` builds the
   URL from the client's own `_base_url` (line 2259 onward) and SigV4 covers `Host`. A URL
   whose host is changed after signing returns `403 SignatureDoesNotMatch`. The split must
   therefore happen *at signing time*, never as a post-hoc string rewrite.
2. **Presigning is not offline by default.** `get_presigned_url` calls `self._get_region(...)`
   (line 2259). `_get_region` (line 477) returns `self._base_url.region` only when the client
   was constructed with an explicit `region=`; otherwise it falls through to
   `_url_open("GET", "us-east-1", query_params={"location": ""})` (line ~496). Because
   `__init__` always sets `self._provider = StaticProvider(...)` when an access key is present
   (line 162), the `not self._provider` early return (line 486) never fires for this app. So a
   client bound to the *public* host would issue `GET /{bucket}?location=` to that host on
   every single presign. A second client without `region=` would have replaced a dial failure
   with a signing failure.

## Goals / Non-Goals

**Goals:**
- Two independent settings: an internal dial target and a public signing origin.
- Presigning that performs **zero** network I/O.
- Backward compatibility: a configuration that sets only `MINIO_ENDPOINT` must behave exactly
  as it does today.
- One probe, at startup, that either succeeds or aborts with a message naming the configured
  endpoint and the fix.
- No urllib3 traceback in application logs for an unreachable store.

**Non-Goals:**
- Rewriting existing presigned URLs. Explicitly forbidden: the signature covers `Host`.
- Changing the chunked upload protocol, the API contract, or the database.
- A reverse proxy, DNS, or TLS work. The public origin stays a configuration value.
- Fixing `TICKET-011` (`PRESIGNED_TTL` documented as seconds, consumed as hours) here.

## Decisions

### 1. `MINIO_ENDPOINT` is the internal target; `MINIO_PUBLIC_ENDPOINT` is the signing origin
The public setting falls back to `MINIO_ENDPOINT` when unset, so every existing deployment
keeps its current behaviour byte for byte while gaining the ability to diverge.
- **Alternative considered (the direction in `openspec/pre_propossals/TICKET-012`):** keep
  `MINIO_ENDPOINT` as the public value and add `MINIO_INTERNAL_ENDPOINT` defaulting to it.
  Rejected: it reads well, but it leaves the variable whose name says "endpoint" pointing at
  the value that cannot be a stable internal name, which is precisely how a LAN IP ended up in
  the internal dial path in the first place. Putting the internal target in the unsuffixed
  name and marking the public one explicitly makes the LAN-IP footgun visible at the point of
  configuration. Both directions are backward compatible, so this is a legibility choice, not
  a correctness one.

### 2. `MINIO_PUBLIC_PORT` and `MINIO_PUBLIC_SECURE` exist alongside the public endpoint
Requirement is only satisfiable with a public host alone on the LAN case (same port, same
scheme as internal). It is *not* satisfiable on the VPS, where the public origin is
`media.example.com:443` over TLS while the internal origin is `minio-acme:9000` over plain
HTTP. Both default to the internal values, so a LAN configuration that sets only
`MINIO_PUBLIC_ENDPOINT` is complete and correct.
- **Alternative considered:** fold scheme and port into a single URL
  (`MINIO_PUBLIC_ENDPOINT=https://media.example.com`). Rejected: it needs custom parsing to
  split back into minio-py's `endpoint` / `secure` / `port` triple, and it makes a typo like a
  trailing slash a runtime failure instead of a configuration error.

### 3. `MINIO_REGION` pins the region on every client
MinIO defaults to `us-east-1` and the running `minio-acme` container sets no `MINIO_REGION`
(only `MINIO_ROOT_USER_FILE` / `MINIO_ROOT_PASSWORD_FILE`), so `us-east-1` is correct here.
It is still configurable, because a MinIO deployed with a real region would otherwise produce
`SignatureDoesNotMatch` on every download — the same class of silent breakage as a wrong host.
Pinning it on the **internal** client too removes a wasted `?location=` round trip that
currently happens on every `bucket_exists` / `put_object` / `list_objects`, since
`get_minio_client()` builds a fresh client per call and therefore never benefits from the
per-instance `_region_map` cache.

### 4. A memoized startup probe replaces the per-upload `ensure_bucket()`
`ensure_bucket()` ran `bucket_exists` (and `make_bucket` on absence) on every single upload.
With minio-py's `Retry(total=5, backoff_factor=0.2)`, one unreachable store became six
connection attempts per photo, which is the retry storm in the log.
- The probe is memoized rather than run-only-once so that a store which comes up after
  startup, or a worker that starts before MinIO, is not permanently poisoned. A failure
  re-raises on the next use with the same actionable message, so the failure mode is "one
  clear error" rather than "the app is silently broken forever".
- The probe runs in the FastAPI lifespan, so `uvicorn` exits non-zero instead of serving
  traffic that cannot possibly succeed. A test suite that never touches MinIO is unaffected:
  `create_app()` is called by `tests/conftest.py` and the probe never dials in tests because
  every test client is a `TestClient` over a mocked storage boundary — the probe is called
  explicitly and the failure path is asserted directly.

### 5. `StorageUnavailableError` is a domain error, raised at the storage boundary
`EHOSTUNREACH` (113), `ECONNREFUSED` (111), `ENETUNREACH` (101), DNS failure and socket timeout
all mean the same thing to a caller: the object store is not reachable at the configured
endpoint. They are translated into `StorageUnavailableError`, whose message names the endpoint,
the container/service to start, and the setting to change. The urllib3 chain is logged once at
`error` level with the original exception, and never re-raised raw.

## Risks / Trade-offs

- **A mis-set public endpoint now fails silently in a new place.** Previously a wrong
  `MINIO_ENDPOINT` broke uploads loudly. Now a wrong `MINIO_PUBLIC_ENDPOINT` produces
  successful uploads and a `403` at photo load time. Mitigation: the post-mortem, the
  `.env.example` text, and the acceptance test all state the constraint, and the deploy
  runbook's §5.5 gate ("fetch a presigned URL from a network that is not the server") is the
  check that catches it.
- **Two settings to keep in sync in the LAN stopgap** (`127.0.0.1` internal, `192.168.10.30`
  public). That is intentional and temporary: the public value must be whatever the phone can
  resolve, and the internal value must never be a lease.
- **Region pinned to `us-east-1`** is correct for this deployment and verified by an actual
  signed round trip in the manual probe, but a MinIO with a custom region needs
  `MINIO_REGION` set. Documented rather than assumed.

## Migration Plan

1. Land the code with the fallback in place (no behaviour change for existing configs).
2. Set `MINIO_ENDPOINT` to the internal target and `MINIO_PUBLIC_ENDPOINT` to the public
   origin in every environment.
3. Restart the backend once; confirm the startup probe logs the internal endpoint.
4. Run the deploy runbook §5.5 external fetch gate.

Rollback: revert the code. The new settings are additive and the fallback keeps the old
single-value configuration working, so rollback requires no config change.

## Open Questions

- Should `MINIO_PUBLIC_ENDPOINT` be rejected at startup when it is a private RFC1918 address?
  Not in this change: a LAN-only rollout is legitimate, and the warning belongs in the
  documentation until a real domain exists. Tracked by the follow-up that introduces the
  reservation/domain.
