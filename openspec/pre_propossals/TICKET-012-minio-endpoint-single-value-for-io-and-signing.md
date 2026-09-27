# Improvement: MINIO_ENDPOINT is used both for internal I/O and for public URL signing

## Metadata

- **Summary**: One setting forces internal traffic through the public TLS edge
- **Issue Type**: Improvement
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: backend, storage, deployment

## Description

`app/core/storage.py` builds one client from `MINIO_ENDPOINT`/`MINIO_PORT`/`MINIO_SECURE` and
uses it for two different purposes:

1. **Server-side I/O** — `put_object` and `stat_object` from inside the API container.
2. **Client-facing URL signing** — `presigned_get_object`, whose output the phone fetches.

Purpose 2 constrains the value to a publicly resolvable host, so purpose 1 is forced through
the public edge. The deployment works around this with a Docker network alias for the media
domain on the Caddy container, which routes the API's own uploads through Caddy and TLS back
into the same host.

**Impact:** every upload and every `stat` call pays a TLS handshake and a proxy hop it does not
need, and the API cannot be moved to a network topology that has no route to its own edge.

## Reproduction

```bash
grep -n "MINIO_ENDPOINT" .env.example app/core/settings.py
grep -n "get_minio_client\|presigned_get_object\|put_object" app/core/storage.py
```

## Notes

- Proposal: add a separate internal endpoint (`MINIO_INTERNAL_ENDPOINT`, defaulting to
  `MINIO_ENDPOINT` for compatibility) used to build the storage client, while
  `MINIO_ENDPOINT` + `MINIO_SECURE` continue to define signed URLs. The public host stays the
  only thing the phone sees, so the `Host`-binding rule is unaffected.
- The `Host`-binding constraint must be preserved exactly: the signing host may never change to
  an internal name.
