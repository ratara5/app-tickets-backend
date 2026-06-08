#!/usr/bin/env bash
set -euo pipefail

# ── Config ───────────────────────────────────────────────────
DB_HOST=""
DB_USER=""
DB_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-host)     DB_HOST="$2";   shift 2 ;;
        --db-user)     DB_USER="$2";     shift 2 ;;
        --db-name)     DB_NAME="$2";     shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

DATA_FOLDER="./data" # /templates/gci
CONTAINER_DATA_DIR="/tmp/csv_load" 

# ── Color Helpers ─────────────────────────────────────────
info()    { echo -e "\e[34m[INFO]\e[0m  $*"; }
warn()    { echo -e "\e[33m[WARN]\e[0m  $*"; }
success() { echo -e "\e[32m[OK]\e[0m    $*"; }

# ── 1. Verify CSV files existencies ───────────────────────────────
csv_files=("$DATA_FOLDER"/*.csv)   # glob secure, not parse ls

if [ ! -e "${csv_files[0]}" ]; then
  warn ".csv files not found en $DATA_FOLDER. Continue without load data."
  exit 0
fi

info "CSVs not found: ${#csv_files[@]}"

# ── 2. Verify db exists ─────────────────
db_exists=$(docker exec "$DB_HOST" psql -U "$DB_USER" -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';")

if [ "$db_exists" != "1" ]; then
  warn "DB'$DB_NAME' doesn't exist. Aborting load."
  exit 1
fi

info "DB '$DB_NAME' verifyed."

# ── 2.0 Hash passwords ─────────────────────────────
info "Hashing passwords..."
python3.12 get_hash.py \
    "$DATA_FOLDER/fsm_users_plain.csv" \
    "$DATA_FOLDER/fsm_users.csv"

# ── 2.1 Transform timezone and other type values before (if venv have 3.12 python3.12 is not necessary ..., only python ...) ───────────────
info "Transform timezone at timezone of data owner user ..."
python3.12 "./transform_csv.py" \
  --data-folder "$DATA_FOLDER" \
  --config "./timezone_config.yml" # /templates/gci/

# ── 3. Copy CSVs to container ─────────────────────────────
docker exec "$DB_HOST" mkdir -p "$CONTAINER_DATA_DIR"
docker cp "$DATA_FOLDER/." "$DB_HOST:$CONTAINER_DATA_DIR/"
info "Files copied to $DB_HOST:$CONTAINER_DATA_DIR"

# ── 4. Iterate and load ───────────────────────────────────────
loaded=()
skipped=()

for filepath in "${csv_files[@]}"; do
  filename=$(basename "$filepath")
  table="${filename%.csv}"

  
  container_path="$CONTAINER_DATA_DIR/$filename"

  # ── 4a. Verify that the table exists in schema ─────────
  table_exists=$(docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT 1 FROM information_schema.tables
     WHERE table_schema='public' AND table_name='$table';")

  if [ "$table_exists" != "1" ]; then
    warn "Table '$table' doesn't exist in '$DB_NAME'. Skipping $filename."
    skipped+=("$table (tabla doesn't exist)")
    continue
  fi

  # ── 4b. Verify that the table is empty ──────────────────
  row_count=$(docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT COUNT(*) FROM \"$table\";")

  if [ "$row_count" -ne 0 ]; then
    warn "Table '$table' already has $row_count rows. Skipping."
    skipped+=("$table ($row_count rows existing)")
    continue
  fi

  # ── 4c. Execute COPY ──────────────────────────────────────
  docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -c \
    "SET datestyle = 'DMY';
    SET session_replication_role = 'replica';
    COPY \"$table\" FROM '$container_path' WITH (FORMAT csv, HEADER true, NULL '');
    SET session_replication_role = 'origin';
    SET datestyle = 'ISO, MDY';"

  success "Loaded: $filename → $table"
  loaded+=("$table")
done

# ── 5. Clean container temp files ────────────
docker exec "$DB_HOST" rm -rf "$CONTAINER_DATA_DIR"
info "Temporal files deleted in container."

# ── 6. Summary ───────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  LOAD SUMMARY"
echo "════════════════════════════════════════"

if [ ${#loaded[@]} -gt 0 ]; then
  success "Loaded tables (${#loaded[@]}):"
  for t in "${loaded[@]}"; do echo "    ✓ $t"; done
else
  warn "No tabla was loaded."
fi

if [ ${#skipped[@]} -gt 0 ]; then
  echo ""
  warn "Skipped tables (${#skipped[@]}):"
  for t in "${skipped[@]}"; do echo "    ✗ $t"; done
fi

echo "════════════════════════════════════════"