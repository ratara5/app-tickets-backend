# Step 14 — Manual endpoint verification with curl

Date: 2026-10-02
Base URL: `http://127.0.0.1:8000` (the container's published loopback port)
Account: the generated local seed account from `infra/local/seed`

Every request below was issued by hand, not through the gate.

## 14.1 Image running, healthcheck healthy

```
$ docker compose -f infra/local/docker-compose.yml up -d
$ docker inspect --format '{{.State.Health.Status}}' <api>
healthy
```

## 14.2 The API imports and serves

```
$ curl -fsS http://127.0.0.1:8000/openapi.json
http 200, 38583 bytes — openapi 3.1.0, 33 paths
```

## 14.3 Login

```
$ curl -X POST http://127.0.0.1:8000/auth/login -d '{"email":"local-seed@example.com","password":"…"}'
token acquired (177 chars)
```

## 14.4 Who am I

```
$ curl http://127.0.0.1:8000/auth/me -H "Authorization: Bearer $TOKEN"
{"user_id":9001,"email":"local-seed@example.com","user_name":"Local Seed User",
 "user_role":"admin","photo_path":null,"created_at":"2026-10-02T17:16:04.776136"}
http 200
```

## 14.5 List tickets

```
$ curl http://127.0.0.1:8000/tickets -H "Authorization: Bearer $TOKEN"
http 200 — []
```

## 14.6 Create, then delete

```
$ curl -X POST http://127.0.0.1:8000/tickets -d '{"ticket_id":9302, …,"priority":"LOW","status":"OPEN","market_id":9001,"equipment_id":9101}'
POST http 201
{"ticket_id":9302,"market_name":"Local Market A","market_city":"Local City A",
 "equipment_name":"EQ-LOCAL-0001 Local Equipment Alpha","assigned_name":null}

$ curl -X DELETE http://127.0.0.1:8000/tickets/9302
DELETE http 204
$ curl http://127.0.0.1:8000/tickets/9302
GET after delete http 404
```

The seeded ids are 9001 (market) and 9101 (equipment), not 1. A first attempt with
`market_id=1, equipment_id=1` returned **500**; see "Defect found" below.

## 14.7 Upload round trip

```
$ printf 'step-14 upload payload: deterministic bytes' > /tmp/payload.bin   # 43 bytes

POST /tickets        → 201  ticket 9303
POST /maintenances   → 201  maintenance 01a0febb-93fa-732a-8623-570dd5a39f30
POST /uploads/init   → 201  upload 01a0febb-9427-72f2-95cf-54777b23537c
POST /uploads/chunk  → 200  {"received_chunks":1,"total_chunks":1,"chunk_index":0}
POST /uploads/complete → presigned URL
```

`sent sha256: ec59a6a8c5c6ee4426a86fe5c1499c03c1d959ef1c41aa6c6a8ec6db3236d3d5`
`got  sha256: ec59a6a8c5c6ee4426a86fe5c1499c03c1d959ef1c41aa6c6a8ec6db3236d3d5`

The presigned URL's host is `127.0.0.1`, which is the public origin here. Locally
the internal dial target and the public origin are the same string, because MinIO
is published on loopback and a client genuinely resolves it. On the VPS they
differ, and the gate checks that case.

`/uploads/chunk` takes `upload_id` and `chunk_index` as **query** parameters, with
only the file as a form field. Sending them as form fields returns 422 naming both
as missing query parameters.

## 14.8 Error cases

| Request | Expected | Got |
| --- | --- | --- |
| `GET /tickets`, no token | 401/403 | **401** |
| `POST /tickets`, no token | 401/403 | **401** |
| `GET /auth/me`, invalid token | 401 | **401** |
| `GET /tickets`, `Authorization: Basic …` | 401 | **401** |
| `GET /tickets/999999` | 404 | **404** |
| `GET /maintenances/<unknown uuid>` | 404 | **404** |
| `POST /uploads/init`, 60 MB declared | policy error | **413** `File too large (max 50 MB)` |
| `POST /uploads/init`, `text/plain` | policy error | **415** `Type not allowed: text/plain` |
| `POST /uploads/init`, `parent_id: "9303"` | validation error | **422** `uuid_parsing` |

## 14.9 Nothing left behind

Baseline re-read after all of the above and diffed against the one captured
before step 13 began:

```
IDENTICAL — steps 13 and 14 left nothing behind
```

Bucket: 0 objects. `alembic_version` still `0003_join_table_keys`.

One row needed removing by hand: the photo left by this step's own upload, under
ticket 9303. The gate's sweep deliberately matches only its own ticket id (9301)
and so did not touch it — which is the correct behaviour on a shared core, and the
reason the manual rows were cleaned with an equally explicit filter.

## Defect found

**An invalid enum value returns 500 instead of a validation error.**

```
$ curl -X POST /tickets -d '{"ticket_id":9304, …,"priority":"urgent", …}'
500
```

API log:

```
sqlalchemy.exc.DataError: (psycopg2.errors.InvalidTextRepresentation)
invalid input value for enum priority_type: "urgent"
```

The same defect is what stopped the gate during this change: `priority` and
`status` are PostgreSQL enums, and nothing validates the value before it reaches
the database. A client sending a typo gets an opaque 500 that names neither the
field nor the allowed values. This is application behaviour, not local-stack
behaviour, and this change alters no endpoint — so it is recorded as a follow-up
in task 17.16 rather than fixed here. The gate sends the real enum labels and the
test suite now reads them out of `infra/schema.sql` so the fixture cannot drift
from the schema again.
