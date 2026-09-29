# Post-mortem: photo uploads down after the MinIO lease moved (2026-09-29)

- **Severity**: total loss of function for maintenance photos in the field
- **Duration**: from the DHCP lease change on the host until the split landed
- **Detected by**: a technician submitting a maintenance with photos
- **Resolved by**: `openspec/changes/split-minio-internal-and-public-endpoints/`
- **Related**: `TICKET-012` (pre-proposal, filed before the outage), mobile lessons 61/62

## Impact

Every maintenance submitted with photos failed. The backend answered with an
`EHOSTUNREACH` traceback naming an internal address, repeated once per photo. Reads were
unaffected: the API kept serving tickets, and photos already delivered to a phone kept
loading, because their signed URLs still pointed at the address that had just disappeared.

## Timeline

| When | Event |
|---|---|
| Before | `MINIO_ENDPOINT=192.168.10.26` in both `.env` and `gtk-companies/gtk-acme/.env`, on a DHCP lease of the Wi-Fi interface |
| 2026-09-29, morning | The host's lease became `192.168.10.30` (confirmed: `192.168.10.30/24` on `wlp2s0`, `dynamic`, and `192.168.10.26` does not answer) |
| 2026-09-29, morning | `minio-acme` restarted with the rest of the stack; healthy, publishing `0.0.0.0:9000-9001` |
| 2026-09-29 | Photo submission fails: `NewConnectionError(HTTPConnection(host='192.168.10.26', port=9000): [Errno 113] No route to host)`, then `GET /acme-uploads-own-api?location=`, per photo |
| 2026-09-29 | `MINIO_ENDPOINT` pointed at a LAN lease in `.env` and in the company `.env`; changed to `127.0.0.1` (what the backend can actually dial) with `MINIO_PUBLIC_ENDPOINT` taking over the phone-facing origin |
| 2026-09-29 | Split implemented, tested (24 new tests) and verified end to end; see "Verification" below |

## Why it worked before, and why it stopped

Nothing in the application changed. The value stopped being true.

The backend runs on the host, and MinIO publishes `0.0.0.0:9000`, so the backend could
always have dialled `127.0.0.1:9000`. It did not, because `app/core/storage.py` built a
**single** MinIO client from `MINIO_ENDPOINT` and used it for two different jobs:

1. **Dialing** — `bucket_exists`, `put_object`, `list_objects`, `remove_object`.
2. **Signing** — `presigned_get_object`, whose output the phone must load.

SigV4 signs the `Host` header, so job 2 forced the value to be an origin the *client* can
resolve. That in turn forbade `localhost` and container names in job 1 — which is why the
only working value was a bare LAN address, a value whose entire lifetime belongs to the
DHCP server. The documentation even encoded the conflation as doctrine: `.env.example`
told the team that `MINIO_ENDPOINT` "must be EXACTLY the host clients use to download
media".

So the system was never broken; it was one DHCP renewal away from broken, and the renewal
arrived. A DHCP lease is a lease: it was always going to move.

Two amplifiers turned one wrong address into an outage instead of a failed request:

- `ensure_bucket()` ran on **every** upload, so the store was probed once per photo, and
  minio-py's `Retry(total=5, backoff_factor=0.2)` turned each probe into six connection
  attempts.
- The failure surfaced as a raw urllib3 traceback naming an internal address, with no
  indication of which setting was wrong or what to set it to.

## Was a recent commit responsible?

**No commit caused it, and that is the finding.** Every layer between the working state
and the outage was correct at the time it was written; the defect is that the value was
*load-bearing for a lease*.

- `.env` is git-ignored, so the address was never in version control and cannot be traced
  to a commit at all.
- The runtime code last changed on 2026-08-28 (`6b8a9c0`), which only **added**
  `delete_object`. The single-client design predates it, from `0976b46` (2026-05-22).
- Two recent commits made the trap *wider*, and this is what deserves attention:
  - `c86fac0` (2026-09-24) added to `docs/development_guide.md` the instruction to use the
    machine's LAN IP, together with a worked example. That is the line someone copied into
    `.env`. It was accurate as written — under the conflated design there was no other
    correct answer.
  - `905b5d3` (2026-09-27) added to `.env.example` the rule that `MINIO_ENDPOINT` must be
    exactly the public host. It turned an accident into doctrine.
- The containerization work (`905b5d3`, and the VPS deploy doctrine in
  `docs/deployment-guide.md`) is the reason the conflation was *known*: the deployment
  papered over it with a Docker network alias for the media domain on the Caddy container,
  routing the API's own uploads out through the public edge and back. That workaround does
  not exist on the LAN host, where the API runs directly, which is why the same defect bit
  harder there than on the VPS.
- The defect was already filed as **`TICKET-012`**, "one `MINIO_ENDPOINT` value is used for
  both internal I/O and public signing", with the fix sketched in the pre-proposal. It was
  filed as *Medium* priority, and nothing about its medium rating was wrong — until the
  lease moved, when it became a field outage.

The honest conclusion: no commit introduced a bug, and every commit that touched the area
followed the design correctly. The design was wrong, it was documented as though it were
right, and the failure was owned by infrastructure nobody watches.

## Contributing factors

1. **One variable, two contradictory requirements** (the root cause).
2. **A network-lease value in application configuration**, with nothing validating that it
   is not a lease.
3. **A probe on the hot path**, turning a configuration error into a per-request retry
   storm.
4. **A configuration error reported as a transport error**, so the log pointed at the
   network instead of at the setting.
5. **A pre-existing ticket rated Medium** whose impact was, in fact, total.
6. **No test asserting anything about the endpoint contract.** Presigned URLs were only
   ever checked through the service layer with a fake, so no test could notice that the
   signed host was a temporary address.

## What fixed it

- `MINIO_ENDPOINT` is the internal dial target only (`127.0.0.1` on the host, `minio-acme`
  in Docker) and is documented as never a LAN address.
- `MINIO_PUBLIC_ENDPOINT` (plus `MINIO_PUBLIC_PORT` / `MINIO_PUBLIC_SECURE`) is the origin
  baked into presigned URLs, falling back to `MINIO_ENDPOINT` when unset so no existing
  configuration changes behaviour.
- `MINIO_REGION` pins the SigV4 region, so pre-signing is local. This was not a
  theoretical concern: a client bound to the public host **without** `region=` issues
  `GET /{bucket}?location=` on every URL, and against an unresolvable public host it failed
  after **6.02 s**. The second client would have replaced the outage with a six-second stall
  per photo.
- The split happens at signing time, never as a rewrite. Verified: a real URL fetched from
  the emulator returns `200` with the exact bytes; the same URL with its host swapped to
  `127.0.0.1` returns `403 SignatureDoesNotMatch`.
- The bucket is checked once in the app lifespan. An unreachable store now aborts startup
  with one message:

  ```
  MinIO is unreachable for bucket check: http://192.168.10.26:9000
  (MINIO_ENDPOINT=192.168.10.26, MINIO_PORT=9000, MINIO_SECURE=false).
  Start or check the MinIO container and confirm that port 9000 is published;
  if the backend runs on the host use MINIO_ENDPOINT=127.0.0.1, and in Docker
  on the acme network use MINIO_ENDPOINT=minio-acme. Never point
  MINIO_ENDPOINT at a LAN address.
  Cause: MaxRetryError <- NewConnectionError <- OSError <- errno 113 (EHOSTUNREACH)
  ```

## Verification (all executed on the affected host)

| Check | Result |
|---|---|
| Startup probe against the dead lease | aborts once, with the message above |
| `POST /uploads/init` → `chunk` → `complete` over HTTP | 201 / 200 / 200 |
| `file_url` host returned by the API | `192.168.10.30:9000` (public), not `127.0.0.1` |
| Fetch that presigned URL from the host | 200, 19 bytes, identical to the upload |
| Fetch it from inside a container (other netns) | 200, 19 bytes |
| Fetch it from the Android emulator over the LAN | 200, `Content-Type: image/png`, 19 bytes, PNG signature intact |
| Same URL with the host rewritten to `127.0.0.1` | 403 `SignatureDoesNotMatch` (host) and 403 from the emulator |
| Pre-signing with an unresolvable public host | 11.86 ms, no network call |
| Full test suite | 255 passed, 23 pre-existing failures identical to `main` (`TICKET-005`), 85% coverage |
| Live database before/after | unchanged (`photos=4`, `uploads_sessions=143`, `fsm_users=15`, `tickets=8`, `maintenances=6`, `worksheets=3`) |

## Action items

| # | Action | Owner | Status |
|---|---|---|---|
| 1 | `MINIO_ENDPOINT` is the internal target; `MINIO_PUBLIC_ENDPOINT` signs the URLs | — | **done** |
| 2 | Region pinned so pre-signing is local | — | **done** |
| 3 | One startup probe, actionable error, no per-upload probe | — | **done** |
| 4 | `.env.example`, `docs/development_guide.md`, `docs/deployment-guide.md` corrected | — | **done** |
| 5 | Replace the LAN stopgap with a **DHCP reservation or a domain** | ratara5 | **open** — the only remaining coupling to a lease |
| 6 | Add a preflight assertion that rejects a private/RFC1918 `MINIO_ENDPOINT` outside an explicit LAN profile | — | open |
| 7 | Treat `TICKET-012`-class "one setting, two owners" defects as release blockers, not Medium | — | open |

## Relation to mobile lessons 61/62

The mobile repository records the mirror image of this incident in lessons **61** and
**62**: the app resolves whatever host the backend signed into the URL, and a
`localhost`-or-lease value produces photos that silently never load. Both sides of this
system were pinned to a temporary address by the same conflation — the backend because it
had to dial it, the app because it had to resolve it. Lesson 61 is the client-side symptom;
lesson 62 is the same value observed from the device. The backend-side rule that closes
both is: **sign with a stable public origin, dial with an internal one, and never rewrite a
signed URL.** This post-mortem and `docs/learned-lessons.md` are the backend-side record of
the same lesson.
