#!/bin/bash
# ========================================
# bootstrap.sh
# Setup db for project local test. App is an infrastructure part and postgres is up by docker compose
#
# Use:
#   ./bootstrap.sh \
#     --project-root ~/Documents/python_scripts/app-tickets-backend \
#     --compose-file docker-compose.yml \
#     --init-file init.sql \
# ========================================
set -euo pipefail

# ── Argumentos ───────────────────────────────────────────────
PROJECT_ROOT=""
COMPOSE_FILE_ARG=""
INIT_FILE_ARG=""

usage() {
    echo "Use: ./bootstrap.sh"
    echo ""
    echo "  --project-root  Project root path (mandatory)"
    echo "  --compose-file  Compose file name (default: docker-compose.yml)"
    echo "  --init-file     Name of creation script init.sql (default: init.sql)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-root) PROJECT_ROOT="$2"; shift 2 ;;
        --compose-file) COMPOSE_FILE_ARG="$2"; shift 2 ;;
        --init-file)    INIT_FILE_ARG="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; usage ;;
    esac
done

[ -z "$PROJECT_ROOT" ] && { echo "✗ --project-root is mandatory"; usage; }

# ── Derivated variables ───────────────────────────────────────
COMPOSE_FILE="${PROJECT_ROOT}/${COMPOSE_FILE_ARG:-docker-compose.yml}"
INIT_SQL="${PROJECT_ROOT}/${INIT_FILE_ARG:-init.sql}" # /templates/gci/
ETL_PATH="$PROJECT_ROOT/etl" # BASE_PATH=.../gci-companies/gci-base/bq-sync-base

# ── Variables loaded via env ─────────────────────
source .env
set -o allexport

# ── Helpers ──────────────────────────────────────────────────
log()  { echo -e "\n\033[1;34m▶ $*\033[0m"; }
ok()   { echo -e "\033[1;32m✓ $*\033[0m"; }
fail() { echo -e "\033[1;31m✗ $*\033[0m"; exit 1; }

# ── Pre-validations ─────────────────────────────────────
log "Verifying dependencies..."
command -v python3.12 >/dev/null || fail "python3.12 not found"
command -v docker     >/dev/null || fail "docker not found"

[ -f "$COMPOSE_FILE" ] || fail "$COMPOSE_FILE"
[ -f "$INIT_SQL"     ] || fail "$INIT_SQL not found"

# ── Python environment ───────────────────────────────────────────
log "Setting up Python environment..."
# cd "$BASE_PATH"

if [ ! -d "venv" ]; then
    python3.12 -m venv venv
    ok "venv created"
else
    ok "venv already exists"
fi

source "${PROJECT_ROOT}/venv/bin/activate"
pip install --quiet -r  "${PROJECT_ROOT}/requirements.txt"
ok "Dependencies have been installed"

# ── Postgres ─────────────────────────────────────────────────
log "Running postgres-gci..."
##1 postgres-gci container exists 
docker start postgres-gci

##2 postgres-gci service already exists in  local docker compose
#- docker compose -f "$COMPOSE_FILE" up -d postgres-gci

##3 postgres-gci service already exists in GoogleCloudProjects
#- docker compose -f "~/Documents/GoogleCloudProjects/$COMPOSE_FILE" up -d postgres-gci

log "Waiting Postgres ready..."
until docker exec postgres-gci pg_isready -U "$DB_USER" >/dev/null 2>&1; do
    echo "  waiting ..."
    sleep 2
done
ok "Postgres ready"

# ── Database ─────────────────────────────────────────────
log "Creating database '$DB_NAME'..."
DB_EXISTS=$(docker exec postgres-gci psql -U "$DB_USER" -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")

if [ "$DB_EXISTS" = "1" ]; then
    ok "Databse '$DB_NAME' already exists"
else
    docker exec postgres-gci psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME"
    ok "Database '$DB_NAME' created"
fi

# ── Init SQL ─────────────────────────────────────────────────
log "Running init.sql..."
docker exec -i postgres-gci psql -U "$DB_USER" -d "$DB_NAME" < "$INIT_SQL"
ok "init.sql executed"

# ── Data load ─────────────────────────────────────────────────
log "Loading initial data..."
cd "$ETL_PATH" 
"$ETL_PATH/seed_db.sh" \
  --db-host "$DB_HOST" \
  --db-user "$DB_USER" \
  --db-name "$DB_NAME"

# ── Configuration load (for companies parameters, better via settings <- TODO) ──
log "Manual load of configuration is required"
CONFIG_DIR="$PROJECT_ROOT/app/config"

# ── Credentials load (for gmail reading)  ───────────────────────────────────
log "Manual load of credential is required"
CRED_DIR="$PROJECT_ROOT/app/credentials"

# ── Start Minio Container ───────────────────────────────────
cd "$PROJECT_ROOT/gtk-companies/gtk-base"
docker compose up -d minio

# ── End ───────────────────────────────────────────────────────
echo -e "\n\033[1;32m✓ ¡¡¡Bootstrap completed!!!\033[0m"
echo "  DB:           $DB_NAME"
echo "  DB user:      $DB_USER"
echo "  Project root: $PROJECT_ROOT"
echo "    "
echo "  Next steps:"
echo "    1. Load configuration"
echo "    2. Load credentials"
echo "    3. Modify .env (¡ONLY if app is running LOCALLY!) ->  DB_HOST=localhost"
echo "    4. Run app: uvicorn app.main:app --reload" # cd app && python3.12 main.py