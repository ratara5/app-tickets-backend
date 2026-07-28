# TK MGM API BACKEND
## SETUP: ONLY FIRST TIME
```bash
export ROOT_PATH=/path/to/your/python/projects/api-tickets-backend
$ROOT_PATH/bootstrap.sh \
    --project-root $ROOT_PATH/app-tickets-backend \
    --compose-file docker-compose.yml \
    --init-file init.sql

uvicorn app.main:app --reload
```  

## RUN: NEXT TIME  
```bash
# Start DB
cd ~/Documents/GoogleCloudProjects #The container is built it from ~/Documents/GoogleCloudProjects/docker-compose.yml, in its db gmail tk are received
docker compose up -d postgres-gci  

# Start MINIO
cd ~/Documents/python_scripts/app-tickets-backend
docker compose up -d minio-acme 

# Serve API
uvicorn app.main:app --reload
```

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
# → [ { "technician_id": 1, "user_id": 1, "user_name": "John Technician" } ]

# Get single technician
curl -X GET /technicians/1 -H "Authorization: Bearer eyJ..."
# → { "technician_id": 1, "user_id": 1, "user_name": "John Technician" }

# List spares
curl -X GET /spares -H "Authorization: Bearer eyJ..."
# → [ { "spare_id": 1, "spare_name": "Filter", "unit": "pcs", "price": 10.5 } ]

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
uvicorn app.main:app --reload
curl http://localhost:8000/openapi.json -o docs/api-spec.json
```  
...

** option b **  
```bash
pip install pyyaml
python3.12 -m scripts.export_openapi
```

`scripts/export_openapi` must exist





