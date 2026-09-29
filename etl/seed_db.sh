#!/usr/bin/env bash
set -euo pipefail

# ── Purpose ────────────────────────────────────────────────────────────────
# Load reference data (units of measure, holidays) and, on explicit request,
# demo/business data into an existing database.
#
# This script is NOT a deployment step. It never creates a database and never
# alters a schema. Production reference data is a deliberate, human-reviewed
# decision; see docs/deployment-guide.md.
#
# What it deliberately does not do: disable triggers or foreign-key checks.
# An earlier version ran every COPY under session_replication_role='replica',
# which switched off all referential integrity for every table it touched and
# was the direct cause of an orphaned spares.unit -> uom.unit row in the live
# database (TICKET-020). Integrity is now enforced by ordering, and by a
# transaction-scoped DEFERRABLE constraint for the single genuinely cyclic
# dependency. A bad reference still fails; it just fails at COMMIT.

# ── Config ─────────────────────────────────────────────────────────────────
DB_HOST=""
DB_USER=""
DB_NAME=""
DATA_FOLDER="./data"
CONTAINER_DATA_DIR="/tmp/csv_load"
ALLOW_BUSINESS_DATA=0
DRY_RUN=0

# ── Helpers ────────────────────────────────────────────────────────────────
info()    { echo -e "\e[34m[INFO]\e[0m  $*"; }
warn()    { echo -e "\e[33m[WARN]\e[0m  $*"; }
success() { echo -e "\e[32m[OK]\e[0m    $*"; }
fail()    { echo -e "\e[31m[FAIL]\e[0m  $*" >&2; exit 1; }

psql_db()    { docker exec "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 "$@"; }
psql_admin() { docker exec "$DB_HOST" psql -U "$DB_USER" -tA "$@"; }

usage() {
    cat <<'EOF'
Usage: ./seed_db.sh --db-host <container> --db-user <role> --db-name <database> [options]

Required:
  --db-host <name>       Running PostgreSQL container name.
  --db-user <role>       Role to connect as. Must be a writer on the target database.
  --db-name <name>       Target database. Must already exist.

Options:
  --data-folder <path>   Directory of CSVs. Default: ./data
  --allow-business-data  Required to load anything other than reference data.
                         This mutates the operational record; see the allowlist
                         below for what that includes.
  --dry-run              Report the plan and exit without writing anything.
  -h, --help             Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-host)             DB_HOST="$2";   shift 2 ;;
        --db-user)             DB_USER="$2";   shift 2 ;;
        --db-name)             DB_NAME="$2";   shift 2 ;;
        --data-folder)         DATA_FOLDER="$2"; shift 2 ;;
        --allow-business-data) ALLOW_BUSINESS_DATA=1; shift ;;
        --dry-run)             DRY_RUN=1; shift ;;
        -h|--help)             usage; exit 0 ;;
        *) echo "Unknown arg: $1"; usage; exit 1 ;;
    esac
done

for required in DB_HOST DB_USER DB_NAME; do
    if [ -z "${!required}" ]; then
        case "$required" in
            DB_HOST) flag="--db-host" ;;
            DB_USER) flag="--db-user" ;;
            DB_NAME) flag="--db-name" ;;
        esac
        fail "Missing $flag. Run with --help."
    fi
done

# ── Load allowlist ─────────────────────────────────────────────────────────
# A CSV filename becomes a table name. Without an allowlist, dropping
# "tickets.csv" into the data folder would COPY straight into the live tickets
# table. The allowlist is the security boundary, so it is explicit and ordered.
#
# Reference data: no dependency on business rows, safe to load anywhere.
REFERENCE_TABLES=(uom holidays)

# Business data: every one of these either depends on other business rows or is
# part of the operational record. Refused unless --allow-business-data.
#
# Note that materials, services and preliquidated are NOT reference data
# despite being unmodelled: materials.maintenance_id and
# services.maintenance_id reference maintenances, and preliquidated.ticket_id
# is NOT NULL and references tickets. They are line items on a live record, so
# loading them is a demo-data decision, never a setup step.
BUSINESS_TABLES=(
    fsm_users
    equipments
    markets
    technicians
    tickets
    maintenances
    spares
    materials
    services
    preliquidated
)

# Cyclic FKs, which ordering alone cannot satisfy: uom.ref_unit -> uom.unit is a
# unit pointing at its own base unit, so a derived unit may legitimately appear
# above its base in the file.
#
# These load through a TEMP staging table and an iterative insert. The schema of
# record is never altered. An earlier attempt used DEFERRABLE INITIALLY DEFERRED
# and had to be abandoned: PostgreSQL refuses to restore NOT DEFERRABLE while
# deferred trigger events are pending, so the constraint stayed permanently
# deferrable, which is a silent production schema change made by a data script.
#
# Format: table:self_reference_column:column_list
SELF_REF_LOADS=("uom:ref_unit:unit,magnitude,uom_description,ref_unit,factor_conversion")

# ── 1. Discover CSVs ───────────────────────────────────────────────────────
if [ ! -d "$DATA_FOLDER" ]; then
    info "No data folder at '$DATA_FOLDER'. Nothing to load."
    exit 0
fi

shopt -s nullglob
all_csvs=("$DATA_FOLDER"/*.csv)
shopt -u nullglob

if [ ${#all_csvs[@]} -eq 0 ]; then
    info "No .csv files in '$DATA_FOLDER'. Nothing to load."
    exit 0
fi
info "Found ${#all_csvs[@]} CSV file(s) in '$DATA_FOLDER'."

# ── 2. Classify, allowlist, order ──────────────────────────────────────────
declare -a plan=()
skipped=()

is_reference() {
    local candidate="$1" t
    for t in "${REFERENCE_TABLES[@]}"; do [ "$t" = "$candidate" ] && return 0; done
    return 1
}
is_business() {
    local candidate="$1" t
    for t in "${BUSINESS_TABLES[@]}"; do [ "$t" = "$candidate" ] && return 0; done
    return 1
}

for filepath in "${all_csvs[@]}"; do
    filename=$(basename "$filepath")
    table="${filename%.csv}"

    if is_reference "$table"; then
        plan+=("$filepath")
    elif is_business "$table"; then
        if [ "$ALLOW_BUSINESS_DATA" -eq 1 ]; then
            plan+=("$filepath")
        else
            warn "'$table' is business data and --allow-business-data was not passed. Skipping."
            skipped+=("$table (business data, needs --allow-business-data)")
        fi
    else
        warn "'$table' is not on the load allowlist. Skipping."
        skipped+=("$table (not on the allowlist)")
    fi
done

# Re-sort into dependency order: reference tables first, then business tables in
# the declared parent-before-child order.
declare -a ordered=()
for t in "${REFERENCE_TABLES[@]}" "${BUSINESS_TABLES[@]}"; do
    for filepath in "${plan[@]}"; do
        [ "${filepath##*/}" = "$t.csv" ] && ordered+=("$filepath")
    done
done
plan=("${ordered[@]+"${ordered[@]}"}")

if [ ${#plan[@]} -eq 0 ]; then
    warn "Nothing eligible to load."
    exit 0
fi

# ── 3. Verify the database exists ──────────────────────────────────────────
db_exists=$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';")
[ "$db_exists" = "1" ] || fail "Database '$DB_NAME' does not exist. This script never creates databases."
info "Target database '$DB_NAME' exists."

# ── 4. Plan output ─────────────────────────────────────────────────────────
echo ""
info "Load plan, in dependency order:"
for filepath in "${plan[@]}"; do
    table="$(basename "$filepath")"; table="${table%.csv}"
    strategy="constraints enforced, in dependency order"
    for c in "${SELF_REF_LOADS[@]}"; do
        [ "${c%%:*}" = "$table" ] && strategy="self-referencing: staged, then inserted parent-before-child"
    done
    echo "    → $table ($strategy)"
done
echo ""

if [ "$DRY_RUN" -eq 1 ]; then
    info "--dry-run: stopping before any write."
    exit 0
fi

# ── 5. Prepare files ───────────────────────────────────────────────────────
# Password hashing is only needed for the demo users, so the reference-only path
# has no Python dependency at all.
if [ -f "$DATA_FOLDER/fsm_users_plain.csv" ]; then
    PYTHON_BIN="${PYTHON_BIN:-}"
    if [ -z "$PYTHON_BIN" ]; then
        for cand in python3.12 python3 python; do
            if command -v "$cand" >/dev/null 2>&1; then PYTHON_BIN="$cand"; break; fi
        done
    fi
    [ -n "$PYTHON_BIN" ] || fail "fsm_users_plain.csv needs hashing but no python3 was found. Set PYTHON_BIN."
    info "Hashing demo user passwords with $PYTHON_BIN..."
    "$PYTHON_BIN" get_hash.py "$DATA_FOLDER/fsm_users_plain.csv" "$DATA_FOLDER/fsm_users.csv"
fi

if [ -f "$DATA_FOLDER/timezone_config.yml" ]; then
    PYTHON_BIN="${PYTHON_BIN:-}"
    if [ -z "$PYTHON_BIN" ]; then
        for cand in python3.12 python3 python; do
            if command -v "$cand" >/dev/null 2>&1; then PYTHON_BIN="$cand"; break; fi
        done
    fi
    [ -n "$PYTHON_BIN" ] || fail "timezone_config.yml needs transform_csv.py but no python3 was found. Set PYTHON_BIN."
    info "Normalising timestamps to the data owner's timezone..."
    "$PYTHON_BIN" ./transform_csv.py --data-folder "$DATA_FOLDER" --config ./timezone_config.yml
fi

docker exec "$DB_HOST" mkdir -p "$CONTAINER_DATA_DIR"
docker cp "$DATA_FOLDER/." "$DB_HOST:$CONTAINER_DATA_DIR/"

# ── 6. Load ────────────────────────────────────────────────────────────────
loaded=()
sql_tmp=$(mktemp /tmp/opencode/seed_load.XXXXXX.sql)

for filepath in "${plan[@]}"; do
    filename="${filepath##*/}"
    table="${filename%.csv}"
    container_path="$CONTAINER_DATA_DIR/$filename"

    table_exists=$(psql_db -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='$table';")
    if [ "$table_exists" != "1" ]; then
        warn "Table '$table' does not exist in '$DB_NAME'. Skipping."
        skipped+=("$table (table missing)")
        continue
    fi

    row_count=$(psql_db -tAc "SELECT COUNT(*) FROM public.\"$table\";")
    if [ "$row_count" -ne 0 ]; then
        info "'$table' already holds $row_count row(s). Leaving untouched."
        skipped+=("$table ($row_count rows existing)")
        continue
    fi

    # Two load strategies, both of which keep referential integrity switched on.
    #
    # Plain table: one transaction, constraints enforced throughout.
    #
    # Self-referencing table: stage into a TEMP table, which has no constraints,
    # then insert in passes so a row is only inserted once its parent is
    # present. The schema of record is never altered.
    self_ref=""; self_col=""; self_cols=""
    for c in "${SELF_REF_LOADS[@]}"; do
        if [ "${c%%:*}" = "$table" ]; then
            rest="${c#*:}"
            self_col="${rest%%:*}"
            self_cols="${rest#*:}"
        fi
    done

    if [ -n "$self_ref" ] || [ -n "$self_col" ]; then
        cat > "$sql_tmp" <<SQL
BEGIN;
SET LOCAL datestyle = 'DMY';
CREATE TEMP TABLE _stage_${table} (LIKE public."${table}" INCLUDING DEFAULTS) ON COMMIT DROP;
COPY _stage_${table} FROM '${container_path}' WITH (FORMAT csv, HEADER true, NULL '');

DO \$resolve\$
DECLARE
    inserted integer;
BEGIN
    LOOP
        INSERT INTO public."${table}" (${self_cols})
        SELECT s.${self_cols//,/, s.}
        FROM _stage_${table} s
        WHERE (s.${self_col} IS NULL OR EXISTS (SELECT 1 FROM public."${table}" p WHERE p.unit = s.${self_col}))
          AND NOT EXISTS (SELECT 1 FROM public."${table}" e WHERE e.unit = s.unit);
        GET DIAGNOSTICS inserted = ROW_COUNT;
        EXIT WHEN inserted = 0;
    END LOOP;

    IF EXISTS (SELECT 1 FROM _stage_${table} s
               WHERE NOT EXISTS (SELECT 1 FROM public."${table}" e WHERE e.unit = s.unit)) THEN
        RAISE EXCEPTION
            'unresolvable rows in ${table}: a ref_unit points outside the file, or the rows form a reference cycle';
    END IF;
END
\$resolve\$;
COMMIT;
SQL
    else
        cat > "$sql_tmp" <<SQL
BEGIN;
SET LOCAL datestyle = 'DMY';
COPY public."${table}" FROM '${container_path}' WITH (FORMAT csv, HEADER true, NULL '');
COMMIT;
SQL
    fi

    # ON_ERROR_STOP makes a failed statement non-zero, so a rejected load aborts
    # the script instead of being reported as a success.
    docker exec -i "$DB_HOST" psql -U "$DB_USER" -d "$DB_NAME" -q -v ON_ERROR_STOP=1 < "$sql_tmp"
    rm -f "$sql_tmp"

    success "Loaded $filename → $table"
    loaded+=("$table")
done

# ── 7. Post-condition: prove integrity instead of assuming it ──────────────
# Previously the trigger bypass meant nothing ever verified the result. Build
# one orphan query per outgoing FK of every loaded table and fail if any row
# points at a parent that is not there.
declare -a loaded_quoted=()
for t in ${loaded[@]+"${loaded[@]}"}; do loaded_quoted+=("'$t'"); done

if [ ${#loaded_quoted[@]} -gt 0 ]; then
    array_list=$(IFS=,; echo "${loaded_quoted[*]}")
    orphan_queries=$(psql_db -tA -c "
        SELECT format(
            'SELECT %L AS fk, count(*) FROM public.%I c LEFT JOIN public.%I p ON c.%I = p.%I WHERE c.%I IS NOT NULL AND p.%I IS NULL',
            c.conrelid::regclass::text || '.' || a.attname || ' -> ' || c.confrelid::regclass::text || '.' || pa.attname,
            c.conrelid::regclass, c.confrelid::regclass, a.attname, pa.attname, a.attname, pa.attname)
        FROM pg_constraint c
        JOIN pg_class cc ON cc.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cc.relnamespace
        JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum  = c.conkey[1]
        JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = c.confkey[1]
        WHERE c.contype = 'f' AND n.nspname = 'public'
          AND c.conrelid::regclass::text = ANY (ARRAY[$array_list]);")

    if [ -n "$orphan_queries" ]; then
        combined=$(echo "$orphan_queries" | paste -sd' UNION ALL ' -)
        while IFS='|' read -r fk count; do
            if [ "${count:-0}" -ne 0 ]; then
                fail "Integrity check failed: $count orphaned row(s) on $fk. Fix the source data and re-run."
            fi
            info "Integrity OK: $fk"
        done < <(psql_db -tA -F'|' -c "$combined")
    fi
fi

# ── 8. Clean up ────────────────────────────────────────────────────────────
docker exec "$DB_HOST" rm -rf "$CONTAINER_DATA_DIR"
info "Removed temporary files from the container."

# ── 9. Summary ─────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  LOAD SUMMARY"
echo "════════════════════════════════════════"
if [ ${#loaded[@]} -gt 0 ]; then
    success "Loaded (${#loaded[@]}):"
    for t in "${loaded[@]}"; do echo "    ✓ $t"; done
else
    warn "No table was loaded."
fi
if [ ${#skipped[@]} -gt 0 ]; then
    echo ""
    warn "Skipped (${#skipped[@]}):"
    for t in "${skipped[@]}"; do echo "    ✗ $t"; done
fi
echo "════════════════════════════════════════"
