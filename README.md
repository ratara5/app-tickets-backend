# TK MGM API BACKEND
## SETUP: ONLY FIRST TIME

> **The schema comes from [`infra/schema.sql`](infra/schema.sql), not from `init.sql`
> and not from the models.**
>
> `init.sql` is retired. It declares a foreign key PostgreSQL refuses (`TICKET-008`),
> and omitted `token_blacklist`, which every authenticated request queries (`TICKET-017`).
> `bootstrap.sh` ran `psql` without `-v ON_ERROR_STOP=1`, so it printed
> `✓ init.sql executed` even when the load failed.
>
> `infra/schema.sql` is a `pg_dump --schema-only` snapshot of the live database:
> 23 tables, labelled generated, carrying its provenance. It is the dev bootstrap
> and the source for the Alembic baseline revision, so the two cannot disagree.
>
> **Do not rebuild the schema from the SQLAlchemy models.** The models are stale
> against the live database — `alembic check` reports 94 pending operations — so a
> script generated from them
> loads cleanly and builds the *wrong* schema — a worse failure than a loud one.
> See `TICKET-019`.

```bash
export ROOT_PATH=/path/to/your/python/projects/api-tickets-backend

# Provision once, as admin. This creates the DATABASE, not its tables.
#   docker exec postgres-gci createdb -U postgres db_gestiket_acme
#
# Then build the schema, as the app role. This creates the TABLES.
#   docker exec -i postgres-gci psql -v ON_ERROR_STOP=1 -U postgres \
#       -d db_gestiket_acme < infra/schema.sql
#
# Two separate steps on purpose. Neither one creates both.
# Full procedure: docs/deployment-guide.md §2.

uvicorn app.main:app --reload --reload-dir app
```

## RUN: NEXT TIME  
```bash
# Start DB
cd ~/Documents/GoogleCloudProjects # The container is built from ~/Documents/GoogleCloudProjects/docker-compose.yml, in its db gmail tk are received
docker compose up -d postgres-gci  

# Start MINIO
cd ~/Documents/GoogleCloudProjects/gci-companies/gci-empresa-a/assync # In order to ilustrate that is possible either one minio for each app or one minio for all apps. Default credentials (both user and pass): minioadmin
docker compose up -d minio-acme 

# Serve API
uvicorn app.main:app --reload --reload-dir app
```

### WHAT THE MINIO CONTAINER CHANGE CHANGED

`minio-acme` now publishes its ports on **loopback only**
(`127.0.0.1:9000`, `127.0.0.1:9001`) instead of on every interface. Two
consequences, both load-bearing:

1. **The VPS stack cannot reach it yet.** `infra/vps/docker-compose.yml` dials
   `minio-acme` by container name on `my-dopamine-network`. Moving MinIO into its own
   compose project did **not** move it onto `my-dopamine-network` — it came up on that
   project's own prefixed network, `assync_as-sync-acme-network`. Compose cannot
   attach a container it does not own, so the attach is a manual step, already
   written into docs/deployment-guide.md §1 and repeated in the compose file:

   ```bash
   docker network connect infra-net minio-acme
   docker network inspect infra-net --format '{{range .Containers}}{{.Name}} {{end}}'
   ```

   Skip it and the API starts and reports healthy, then every upload and every
   photo download fails on DNS resolution. Nothing warns you at boot.

2. **A phone on the LAN can no longer load media.** Presigned URLs are signed
   with `MINIO_PUBLIC_ENDPOINT`, and with the S3 port bound to loopback there is
   no longer a listener at any LAN address. For local device testing, pick one:
   publish the S3 port on the LAN again (`"9000:9000"` in the MinIO compose), or
   forward it with an `alpine/socat` tunnel as `provider-portal-minio-dev-tunnel`
   does, or point the app at Caddy. For the VPS this is a non-issue: Caddy is the
   only public listener and terminates TLS for `MEDIA_DOMAIN`.

   `MINIO_PUBLIC_ENDPOINT` in `.env` was `192.168.10.30`, which is not this host
   (`192.168.10.31`) and does not answer on the LAN at all, so every URL the API
   handed out was dead on arrival. The LAN-correct value is the machine's mDNS
   name, `ratara5-SVT15115CLS.local`, which avahi publishes and a phone on the
   same LAN resolves directly. A name rather than an address, because this key is
   signed into every URL and must not move when a DHCP lease rotates.

   `.env` currently holds `MINIO_PUBLIC_ENDPOINT=127.0.0.1`, which is correct
   *only* while the app runs in a simulator or another on-host client that shares
   this host's loopback namespace — that is why photos render there. It is not a
   LAN value: all of `127.0.0.0/8` is unreachable from any other device, so
   `127.0.0.1` or `127.0.0.2` signed into a URL fails on a real handset every
   time. Set this key to `ratara5-SVT15115CLS.local` (or a DHCP-reserved LAN
   address) before testing on a physical device.

### THE BUCKET AND ITS VOLUME ARE A SEPARATE PROBLEM

The port binding was necessary but not sufficient. `minio-acme` now runs under
the `assync` compose project, so its volume is `assync_acme_minio_data`, which is
**empty**. The 34 objects uploaded before the move are in
`infrastructure-companies-v2_acme_minio_data`, under the bucket
`acme-uploads-own-api`. A fresh `minio-acme` therefore serves no photos, and no
port binding changes that.

`.env` names `tecfrio-uploads-own-api` as `MINIO_DEFAULT_BUCKET`. That bucket did
not exist on the new volume, so the API failed its startup bucket check with
`AccessDenied` until the bucket and a service account scoped to it were created
(`tecfrio_access_key`, policy limited to that single bucket — not root
credentials, per `.env.example`).

Before this carries real traffic, decide which of these is true, because they are
not equivalent:

- **the historical objects are wanted** — attach the volume that holds them
  (`infrastructure-companies-v2_acme_minio_data`) and set
  `MINIO_DEFAULT_BUCKET=acme-uploads-own-api`
- **the new empty bucket is wanted** — nothing to migrate, but every photo
  referenced by an existing `photos` row is then a dead link that needs clearing
  or re-uploading <<<==== THIS OPTION WAS SELECTED!! 

Check with `mc ls local/<bucket> --recursive | wc -l`, never with a bucket
existence test: an empty bucket satisfies every check the API makes.

### TWO ORIGINS, TWO RUN MODES — DO NOT MIX THEM

`MINIO_ENDPOINT` is where *this process* dials the store; `MINIO_PUBLIC_ENDPOINT`
is the origin baked into presigned URLs, which the phone must resolve. They are
deliberately different values in the VPS stack, and `infra/vps/docker-compose.yml`
now pins both for the container instead of inheriting them from `.env`, because
`.env` is the host-run file where `MINIO_ENDPOINT=127.0.0.1` is correct and
`127.0.0.1` inside a container is the container itself.

## API USAGE  
```bash
# 1. Register (creates user + returns token)
curl -X POST /auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","user_name":"User","password":"secret123","user_role":"TECHNICIAN"}'
# → { "access_token": "eyJ..." }

# 2. Login (returns token)
curl -X POST /auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret123"}'
# → { "access_token": "eyJ..." }

# 3. List tickets (using token)
curl -X GET /tickets \
  -H "Authorization: Bearer eyJ..."
# → [ { "ticket_id": 1, "ticket_description": "...", ... } ]

# 4. Get single ticket
curl -X GET /tickets/1 \
  -H "Authorization: Bearer eyJ..."
# → { "ticket_id": 1, ... }

# 5. Create ticket
curl -X POST /tickets \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"1","ticket_date":"2026-07-07T00:00:00","ticket_description":"Broken pump","priority":"NORMAL","status":"OPEN","market_id":1,"equipment_id":1}'
# → 201 { "ticket_id": 1, ... }

Prerequisites for POST: market_id and equipment_id must reference existing rows in markets and equipments tables (TICKET-001 fix). The /tickets endpoints require a valid JWT Bearer token from /auth/login or /auth/register.
```  
### TICKET LIFECYCLE
OPEN -> ASSIGNED -> IN PROGRESS -> CLOSED  
OPEN -> CANCELLED  
IN PROGRESS -> PAUSED  

### MASTER DATA ENDPOINTS  
```bash
# List technicians
curl -X GET /technicians -H "Authorization: Bearer eyJ..."
# → [ { "technician_id": 1, "user_name": "John Technician" } ]

# Get single technician
curl -X GET /technicians/1 -H "Authorization: Bearer eyJ..."
# → { "technician_id": 1, "user_name": "John Technician" }

# List spares
curl -X GET /spares -H "Authorization: Bearer eyJ..."
# → [ { "spare_id": 1, "spare_name": "Filter", "price": 10.5 } ]

# Get single spare
curl -X GET /spares/1 -H "Authorization: Bearer eyJ..."
# → { "spare_id": 1, "spare_name": "Filter", ... }

# List markets
curl -X GET /markets -H "Authorization: Bearer eyJ..."
# → [ { "market_id": 1, "market_name": "Market A", "city": "City", "transport_cost": 100 } ]

# Get single market
curl -X GET /markets/1 -H "Authorization: Bearer eyJ..."
# → { "market_id": 1, ... }

# List equipment
curl -X GET /equipments -H "Authorization: Bearer eyJ..."
# → [ { "equipment_id": 1, "equipment_name": "Pump" } ]

# Get single equipment
curl -X GET /equipments/1 -H "Authorization: Bearer eyJ..."
# → { "equipment_id": 1, ... }

# List labsdls (laboratory standards)
curl -X GET /labsdls -H "Authorization: Bearer eyJ..."
# → [ { "labsdl_id": 1, "labsdl_name": "Normal", "labsdl_description": "", "hourly_rate": 50 } ]

# Get single labsdl
curl -X GET /labsdls/1 -H "Authorization: Bearer eyJ..."
# → { "labsdl_id": 1, ... }
```
All master data endpoints support `page` and `page_size` query parameters (defaults: page=1, page_size=50).

### PERMANENT DATA  
*Ticket 1:* CLOSED  
Checked States: OPEN, IN PROGRESS  
*Ticket 2:* CANCELLED  

## GIT NOTES  
### You need to know if any comit in branch main was written after the creation of a branch any-other-branch 
```bash
# Find the common ancestor (where the branch was created from)
base=$(git merge-base main any-other-branch)

# List commits on main made after that point
git log $base..main
```  

### You need to do a real dry-run merge (Safe, Reversible)  
```bash
git checkout main
git pull
git merge --no-commit --no-ff any-other-branch
git status
git merge --abort
```

### You need to update the branch main from branch any-other-branch 
```bash
git checkout main
git merge any-other-branch
git status
# Reolve conflicts (if there are any) 
# git add <resolved-file>
git push origin main
git commit -m "Merge branch 'any-other-branch' into main"
git push
```  

### API USAGE IN POSTMAN  
The use of POSTMAN DESKTOP APP is REQUIRED.
**There, import `app-tickets-backend.postman_collection.json`**  

### DB USAGE
```bash
docker exec -it postgres-gci psql -U postgres

\c db_gestiket_acme
```

## IMPLEMENTING OPENSPEC  
Open spec is a npm package + repo in order to add agentic layer  
see https://github.com/LIDR-academy/lidr-specboot/tree/main  
Next, a summmary of lidr-specboot/README.md (and expand the instructions for items applicable to this project):  

### 1. Install and initialize openspec   
If use nvm:
```bash
install nvm --lts
nvm alias default lts/*
node --version # min 24.16.0
npm install -g @fission-ai/openspec@latest
openspec init # IN OTHER TERMINAL!
```
...

### 2. Import into your project 
... and commit: `chore: add agentic layer config (OpenSpec/specboot) (wip)`

### 3. Customize `/docs` for your project (Mandatory)  
** 3.1 Generate `api-spec.json` **  

** option a **

```bash
docker compose up -f ~/Documents/GoogleCloudProjects/docker-compose.yml postgres-gci
uvicorn app.main:app --reload --reload-dir app
curl http://localhost:8000/openapi.json -o docs/api-spec.json
```  
...

** option b **  
```bash
pip install pyyaml
python3.12 -m scripts.export_openapi
```

`scripts/export_openapi` must exist





