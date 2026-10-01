# Split MINIO_ENDPOINT into an internal dial target and a public signing origin

## Why

Submitting a maintenance with photos is a hard outage:

```
NewConnectionError("HTTPConnection(host='192.168.10.26', port=9000):
Failed to establish a new connection: [Errno 113] No route to host"): /acme-uploads-own-api?location=
```

repeated once per photo. The host is `192.168.10.26`, a DHCP lease on a Wi-Fi interface. The
machine is now `192.168.10.30`; `.26` is not bound to any interface and does not route.

The lease is not the root cause, it is the trigger. `app/core/storage.py` builds **one** MinIO
client from `MINIO_ENDPOINT` and uses it for two unrelated jobs:

1. **Dialing the store** — `bucket_exists`, `put_object`, `list_objects`, `remove_object`.
2. **Signing the URLs the phone must load** — `presigned_get_object`.

SigV4 signs the `Host` header, so job 2 forces the value to be an origin the *client* can
resolve. That in turn forbids job 1 from using `localhost` or a container name, which is why
the only working value was a bare LAN IP — a value whose entire lifetime is owned by the DHCP
server. The documentation encodes the conflation as doctrine: `.env.example:50` states that
`MINIO_ENDPOINT` "must be EXACTLY the host clients use to download media".

So a routine lease rotation on a Wi-Fi client took down every photo upload in the field. The
same defect is already filed as `TICKET-012` ("one `MINIO_ENDPOINT` value is used for both
internal I/O and public signing") and is still open.

Two amplifiers turn one wrong IP into an outage instead of a failed request:

- `ensure_bucket()` runs on **every** upload, so the store is probed once per photo, and
  minio-py's `Retry(total=5, backoff_factor=0.2)` turns each probe into a retry storm.
- The failure surfaces as a raw urllib3 `NewConnectionError` traceback naming an internal
  address, with no indication of which setting is wrong or how to fix it.

## What Changes

- **BREAKING (config only)**: `MINIO_ENDPOINT` becomes the **internal dial target** only
  (`127.0.0.1` host-run, `minio-acme` in Docker). It must never be a LAN IP again.
- New `MINIO_PUBLIC_ENDPOINT` (plus optional `MINIO_PUBLIC_PORT` / `MINIO_PUBLIC_SECURE`)
  is the origin baked into presigned URLs. It falls back to `MINIO_ENDPOINT` when unset, so
  every existing configuration keeps behaving exactly as it does today.
- New `MINIO_REGION` (default `us-east-1`) pins the SigV4 region, making presigning purely
  local: without it minio-py issues `GET /{bucket}?location=` against the public host on
  **every** presign (`minio/api.py:2259` → `_get_region` → `_url_open`).
- `get_presigned_url()` signs with a client bound to the public endpoint. No call site may
  rewrite a presigned URL — the signed `Host` makes any rewrite a `SignatureDoesNotMatch`.
- `ensure_bucket()` stops running per upload: a single memoized startup probe replaces it, and
  a failure aborts startup with one actionable message naming the configured endpoint.
- Connection-refused / no-route / DNS failures are translated into a domain error
  (`StorageUnavailableError`) instead of leaking an urllib3 traceback.
- Documentation: `.env.example` (the conflation note is replaced), `docs/development_guide.md`
  (drops the hardcoded `192.168.10.26`), `docs/deployment-guide.md` (closes `TICKET-012`),
  and a post-mortem that cross-references mobile lessons 61/62.

## Capabilities

### New Capabilities
- `minio-endpoint-split`: separate internal dial target from public signing origin, presign
  offline against a pinned region, and fail fast with an actionable error when the store is
  unreachable.

### Modified Capabilities
- (none — no existing OpenSpec capabilities are defined yet)

## Impact

- **Code**: `app/core/settings.py`, `app/core/storage.py`, `app/server.py` (startup probe).
- **Config**: `.env` and `gtk-companies/gtk-acme/.env` (untracked, this host only);
  `.env.example`; `infra/vps/*` documentation.
- **Tests**: new `tests/test_minio_endpoints.py`; `tests/test_uploads.py` and
  `tests/test_worksheets.py` if the startup probe changes their fixtures.
- **Docs**: `.env.example`, `docs/development_guide.md`, `docs/deployment-guide.md`,
  `docs/learned-lessons.md`, `docs/post-mortems/2026-09-29-minio-endpoint-lease-outage.md`.
- **No DB migration**: no schema, no endpoint, no request/response field changes. The API
  contract is untouched.
- **Frontend (separate project)**: no change required. The app keeps receiving presigned URLs
  in the same fields; only their host origin is now configured independently.
