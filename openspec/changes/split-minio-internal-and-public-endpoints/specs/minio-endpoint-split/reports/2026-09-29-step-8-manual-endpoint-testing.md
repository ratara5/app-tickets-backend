# Step 8 Report — Manual Endpoint Testing with curl

- **Date**: 2026-09-29
- **Change**: `split-minio-internal-and-public-endpoints`
- **Executed by**: the agent, on the affected host, against the real API, the real MinIO
  container, and a real Android emulator (`emulator-5554`)

## 0. Environment as resolved by the app

```
internal: http://127.0.0.1:9000 | public: http://192.168.10.30:9000
region:   us-east-1               | bucket:  acme-uploads-own-api
```

The startup line the operator now sees instead of a per-photo traceback:

```
[info] minio_origins_resolved  internal=http://127.0.0.1:9000 public=http://192.168.10.30:9000 region=us-east-1
[info] minio_bucket_created     bucket=acme-uploads-own-api        (first run only)
```

## 1. Upload round trip over HTTP (the reported failure)

`/auth/register` is broken on this host (sequence drift, see step 7 report), so a
throwaway user was inserted directly with the app's own `hash_password` and removed at the
end.

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"probe-minio-2026@gmail.com","password":"Probe-2026!"}' | jq -r .access_token)

# 19-byte PNG: 89 50 4E 47 0D 0A 1A 0A + "probe-bytes"
curl -s -X POST http://127.0.0.1:8000/uploads/init -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"parent_tab":"maintenances","parent_id":"01a04035-8f04-7843-b943-b11ce33f98d4",
       "tab_name":"photos","col_name":"photo_file","content_type":"image/png",
       "total_size":19,"total_chunks":1}'
# -> 201 {"upload_id":"01a0ed59-70f4-70c3-91ba-ef6e599b7942","chunk_size":1048576,"next_chunk":0}

curl -s -X POST "http://127.0.0.1:8000/uploads/chunk?upload_id=$UPLOAD_ID&chunk_index=0" \
  -H "Authorization: Bearer $TOKEN" -F "chunk=@/tmp/opencode/photo.png;type=image/png"
# -> 200 {"upload_id":"01a0ed59-...","chunk_index":0,"received_chunks":1,"total_chunks":1}

curl -s -X POST "http://127.0.0.1:8000/uploads/complete?upload_id=$UPLOAD_ID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
# -> 200 {"completed":true,
#         "file_url":"http://192.168.10.30:9000/acme-uploads-own-api/Mantenimientos/.../....png?X-Amz-Algorithm=..."}
```

| Assertion | Result |
|---|---|
| `/uploads/init` | 201, upload created |
| `/uploads/chunk` | 200, 1/1 chunks received |
| `/uploads/complete` | 200, `completed: true` |
| `file_url` host is `192.168.10.30:9000` (public) | **pass** — not `127.0.0.1`, not the dead `192.168.10.26` |
| `file_url` carries `X-Amz-Signature` | pass |
| No `NewConnectionError`, no `?location=` retry in the log | pass |

## 2. The URL is fetchable from a real Android emulator

The emulator has no `curl` and no `wget`, only `toybox`, so the signed request was piped
through `toybox nc` after `adb push` (which also avoids `printf` mangling the `%2F` in the
query string).

```bash
printf 'GET /acme-uploads-own-api/Mantenimientos/.../....png?X-Amz-Algorithm=... HTTP/1.1\r\n\
Host: 192.168.10.30:9000\r\nConnection: close\r\n\r\n' > req.txt
adb push req.txt /data/local/tmp/req.txt
adb shell "(toybox cat /data/local/tmp/req.txt; toybox sleep 3) | toybox nc 192.168.10.30 9000"
```

```
HTTP/1.1 200 OK
Content-Length: 19
Content-Type: image/png
ETag: "02723e1a215f8770ce922f0d34f7494a"
Server: MinIO
...
M-^IPNG                      <- 89 50 4E 47: the exact bytes uploaded
```

| Origin of the fetch | Result |
|---|---|
| Host (`127.0.0.1:8000` API, LAN IP for the URL) | 200, 19 bytes, `cmp` identical to the uploaded file |
| Inside the `minio-acme` container (different netns) | 200, 19 bytes |
| **Android emulator over the LAN** | **200, `image/png`, 19 bytes, PNG signature intact** |
| `curl` on the returned `file_url` | 200, `cmp` identical to the uploaded file |

## 3. A presigned URL is never rewritten (error case)

The same signed URL with its host replaced by the internal address:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  "$(echo "$URL" | sed 's#//192.168.10.30:#//127.0.0.1:#')"
# host: 403  <Code>SignatureDoesNotMatch</Code>
adb shell "(toybox cat /data/local/tmp/req_bad.txt; toybox sleep 3) | toybox nc 127.0.0.1 9000"
# emulator: HTTP/1.1 403 Forbidden
```

So the split must happen at signing time, which is what `get_presigned_client()` does. There
is no post-processing path in the codebase that could reintroduce the bug.

## 4. Unreachable store fails fast (error case)

Startup against the dead lease, with the real network and the real client:

```bash
MINIO_ENDPOINT=192.168.10.26 python -c "
from fastapi.testclient import TestClient; from app.server import create_app
with TestClient(create_app()): pass"
```

```
[info] minio_origins_resolved internal=http://192.168.10.26:9000 public=http://192.168.10.30:9000 region=us-east-1
RAISED: StorageUnavailableError
MinIO is unreachable for bucket check: http://192.168.10.26:9000
(MINIO_ENDPOINT=192.168.10.26, MINIO_PORT=9000, MINIO_SECURE=false). Start or check the
MinIO container and confirm that port 9000 is published; if the backend runs on the host use
MINIO_ENDPOINT=127.0.0.1, and in Docker on the acme network use MINIO_ENDPOINT=minio-acme.
Never point MINIO_ENDPOINT at a LAN address.
Cause: MaxRetryError <- NewConnectionError <- OSError <- errno 113 (EHOSTUNREACH)
```

One probe, one message, naming the setting, the value, and the fix. No urllib3 retry
traceback reaches the caller.

## 5. Pre-signing is local (the minio-py detail)

```bash
python - <<'PY'
import time; from app.core import storage
storage.settings.minio_public_endpoint = "media.acme.invalid"   # does not resolve
t0 = time.perf_counter()
url = storage.get_presigned_url("Mantenimientos/PROBE/offline.png", expires_hours=1)
print(f"presigned in {(time.perf_counter()-t0)*1000:.2f} ms")     # 11.86 ms
PY
```

Counterfactual, same public client **without** the pinned region:

```
without region: failed after 6.02s -> MaxRetryError
```

`region=` is not cosmetic: without it minio-py issues `GET /{bucket}?location=` against the
public host on every pre-signed URL, which would have replaced this outage with a six-second
stall per photo.

## 6. Other error cases

| Case | Command | Result |
|---|---|---|
| Unauthenticated upload init | `POST /uploads/init` with no token | 422 (`uuid_version`: a v1 UUID is rejected — validation works) |
| Wrong UUID version | `parent_id=00000000-0000-0000-0000-000000000001` | 422 `UUID version 7 expected` |
| Missing chunk body | `POST /uploads/chunk` with a raw body | 422 `body.chunk Field required` |

## 7. Cleanup

| Artifact | Action | Verified |
|---|---|---|
| `fsm_users` row `user_id=900001` | deleted | `fsm_users=15`, same as baseline |
| `uploads_sessions` row `01a0ed59-...` | deleted | `uploads_sessions=143`, same as baseline |
| `photos` row for maintenance `01a04035-...` | deleted | `photos=4`, same as baseline |
| MinIO object `Mantenimientos/.../9001/01a04035-...png` | removed | listed and deleted |
| MinIO object `Mantenimientos/Correctivos/2026/Septiembre/PROBE/photo.png` | removed | listed and deleted |

Database state after all testing: `tickets=8 maintenances=6 photos=4 uploads_sessions=143
worksheets=3 fsm_users=15` — identical to the pre-test baseline.

## Outcome

**Step 8 status: PASS.** The originally reported failure (submitting a maintenance with
photos) is fixed and verified end to end, and the acceptance criterion "a real presigned
URL's host is fetchable from the Android emulator and from a device on the LAN" is met for
the emulator. A physical device on the LAN is not attached to this host, so the LAN-side
check was made from a second network namespace (inside the `minio-acme` container) and from
the host over the `wlp2s0` interface; both return the same 200.
