#!/usr/bin/env bash
#
# `make gate-local` — prove the local environment actually works, end to end.
#
# WHAT THIS IS NOT
#   It is not a health check. `/openapi.json` is already liveness — the image's own
#   HEALTHCHECK (Dockerfile) uses it — and a readiness route would be that same
#   check renamed. Neither touches a dependency: a liveness probe proves the
#   process serves, a readiness probe proves it is accepting, and a broken
#   database, wrong credentials or a missing migration pass both. So no such
#   endpoint is added here. The gate drives the real API instead, through the same
#   routes a client uses, so a wrong JWT_SECRET or a missing token_blacklist table
#   fails it.
#
# IT EXERCISES THE RUNNING IMAGE, NOT A TEST DOUBLE
#   Every check runs against the container started by `make setup-local`, or over
#   HTTP against its published port. No sqlite, no monkeypatched Minio client, no
#   `psql` standing in for the application path. `tests/conftest.py` does exactly
#   those things, which is why a suite passing against it says nothing about the
#   image; see tasks.md §10.14.
#
# READ-ONLY EXCEPT WHERE IT CLEANS UP AFTER ITSELF
#   The gate creates one ticket and one object, then removes both, so a repeated
#   run does not accumulate state. It never stops or removes a container, and it
#   never touches the shared core's lifecycle.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/infra/local/docker-compose.yml"
ENV_FILE="${PROJECT_ROOT}/.env"

# Resolved from the compose file in main(), for the same reason setup.sh does it
# there: the hardcoded tag `app-tickets-backend:api-local` is never built, so the
# summary reported "image unknown" for a stack that was running correctly.
API_IMAGE=""

# The upload's parent is the maintenance this gate creates, not a synthetic id.
#
# `parent_id` must be a UUID, and `maintenances` is the only domain table whose
# primary key is one -- `tickets` and every other entity use integer ids, so a
# ticket cannot be the parent at all (Pydantic rejects it with uuid_parsing).
#
# A fixed UUID looked safe because `POST /uploads/init` persists a session
# without loading the parent. `POST /uploads/complete` does load it and 404s when
# it is absent (app/services/upload_service.py:172), so the parent must be a row
# that really exists. verify_maintenance creates one through the API.
GATE_PARENT_TAB="maintenances"
GATE_TICKET_DESCRIPTION="gate-local verification — created and deleted by make gate-local"

# Names this script owns; `.env` may not define them. See setup.sh for why.
RESERVED_KEYS="COMPOSE_PROJECT_NAME COMPOSE_FILE ENV_FILE API_IMAGE"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
    YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
    BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; RESET=""
fi

declare -a RESULTS=()
CREATED_TICKET_ID=""
CREATED_MAINTENANCE_ID=""
CREATED_OBJECT_KEY=""
CREATED_BUCKET=""

# Always armed. Colour is a TTY concern; the failure summary is not, and hiding
# it behind `[ -t 1 ]` meant a failing gate in CI printed nothing at all beyond
# the FAILED line -- which is exactly where a summary matters most.
gate_on_exit() {
    local rc=$?
    # Leaving rows behind makes the NEXT run fail for the wrong reason: a gate
    # that dies between creating ticket 9301 and deleting it leaves a primary key
    # behind, and the rerun then reports `duplicate key value violates unique
    # constraint "tickets_pkey"` -- pointing at the ticket id instead of at
    # whatever actually broke the first run.
    if [ "$rc" -ne 0 ]; then
        remove_object
        cleanup
    fi
    print_summary failed
}
trap gate_on_exit EXIT

step() { printf '\n%s==>%s %s%s%s\n' "$BOLD" "$RESET" "$BOLD" "$1" "$RESET"; }
info() { printf '    %s\n' "$1"; }
dim()  { printf '    %s%s%s\n' "$DIM" "$1" "$RESET"; }
pass() { RESULTS+=("$1|pass"); printf '    %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { RESULTS+=("$1|warn"); printf '    %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()  { RESULTS+=("${CURRENT_CHECK:-gate}|FAIL"); printf '\n%sFAILED:%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }

current_check() { CURRENT_CHECK="$1"; }

# ── .env, read the same way setup-local reads it ────────────────────────────
load_env() {
    [ -f "$ENV_FILE" ] || die ".env is missing. Run make setup-local first."
    local line key value
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; *=*) ;; *) continue ;; esac
        key="${line%%=*}"; value="${line#*=}"
        case "$value" in
            \"*\") value="${value%\"*}"; value="${value#\"}" ;;
            \'*\') value="${value%\'*}"; value="${value#\'}" ;;
            *)     value="${value%%#*}"; value="${value%"${value##*[![:space:]]}"}" ;;
        esac
        key="${key%"${key##*[![:space:]]}"}"
        case "$key" in [A-Za-z_]*) ;; *) continue ;; esac
        # `.env` may not define the gate's own structural variables; see setup.sh
        # for the full explanation. COMPOSE_PROJECT_NAME matters most here: it
        # decides which containers the gate inspects.
        case " $RESERVED_KEYS " in
            *" ${key} "*) warn ".env defines ${key}, which this script owns; ignoring it" ; continue ;;
        esac
        printf -v "$key" '%s' "$value"
        # Exported, not just set. `docker compose run -e KEY` reads the value from
        # this process's ENVIRONMENT, so a plain shell variable is invisible to it
        # and the migrate job started with an empty environment -- which fails as
        # a wall of pydantic "Field required" errors rather than as a missing
        # variable, so the cause was not obvious from the message.
        export "${key}=${value}"
    done < "$ENV_FILE"
}

# Names come from the same identifiers `make setup-local` provisioned — one source,
# so the gate cannot drift from what was created and start asserting against a
# database that was never built. None of them is written literally in this file;
# tests/test_local_assets.py enforces that (§10.3).
require_env() {
    local key
    for key in "$@"; do
        [ -n "${!key:-}" ] || die "$key is not set in .env (see .env.example)."
    done
}

# The value the RUNNING CONTAINER was given, not the value in .env. The two can
# differ, and it is the container's value that decides where writes land.
container_env() {
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$1" \
        | grep -E "^$2=" | head -1 | cut -d= -f2-
}

# The API container is addressed by the id compose reports, never by a guessed
# name. The services here set no `container_name`, so the real name is
# `<project>-api-1`; `docker inspect api` looks for a container literally named
# "api", does not resolve compose service names, and fails with
# "No such object: api". That surfaced as the gate refusing to run at all.
api_container_id() {
    docker compose -f "$COMPOSE_FILE" ps -q api
}

api_exec() {
    docker compose -f "$COMPOSE_FILE" exec -T api "$@"
}

# ── cleanup, so a repeated run does not accumulate state ────────────────────
# Idempotent and safe when nothing was created. Ordered child-before-parent: the
# maintenance is what the upload session points at.
cleanup() {
    if [ -n "$CREATED_MAINTENANCE_ID" ]; then
        curl -sS -o /dev/null -X DELETE \
            -H "Authorization: Bearer ${TOKEN:-}" \
            "${API_BASE}/maintenances/${CREATED_MAINTENANCE_ID}" || true
        dim "cleaned up maintenance ${CREATED_MAINTENANCE_ID}"
        CREATED_MAINTENANCE_ID=""
    fi
    if [ -n "$CREATED_TICKET_ID" ]; then
        curl -sS -o /dev/null -X DELETE \
            -H "Authorization: Bearer ${TOKEN:-}" \
            "${API_BASE}/tickets/${CREATED_TICKET_ID}" || true
        dim "cleaned up ticket ${CREATED_TICKET_ID}"
        CREATED_TICKET_ID=""
    fi
}

# ── preflight, so a crashed earlier run does not fail this one ──────────────
# Not the same job as cleanup(). cleanup() knows the ids THIS run created and can
# remove them through the API; it knows nothing about rows a previous run died on.
# A run killed between creating its rows and cleaning them up leaves a primary key
# and an upload session behind, and the next run fails on that primary key before
# reaching the check that was actually broken -- reporting `duplicate key value
# violates unique constraint "tickets_pkey"`, which points at the ticket id
# instead of at whatever went wrong the first time.
#
# Only two classes of row are removed, both unusable and both in this project's
# own database:
#   1. upload sessions whose parent maintenance does not exist. complete 404s on
#      those, and the application exposes no route that removes them, so they can
#      never be finished or deleted through the API.
#   2. the ticket this gate creates and any maintenance under it, left behind by a
#      run that never reached its delete step.
# Removes the rows a gate run leaves behind. Called twice: before the checks, to
# clear what an earlier run left, and after them, to clear what this run left.
#
# Two kinds, and neither can be removed through the API:
#
#   1. upload sessions whose parent maintenance is gone. `complete` 404s on those
#      and no route deletes them, so they can never be finished or discarded.
#   2. photo rows. Completing an upload inserts into `photos` with a NULL
#      `maintenance_id` -- the service stores the path but does not attach the row
#      to its parent -- so `DELETE /maintenances/{id}` cannot reach them, and the
#      foreign key is NO ACTION. Each run therefore left one more row behind. They
#      are matched on the ticket id embedded in the stored path, which is what
#      makes the delete this gate's own and nobody else's.
#
# The application exposes no route that removes an upload session, so this is the
# only way to do it. It is also why a session whose parent no longer exists is safe
# to delete rather than merely untidy: `complete` 404s on it and nothing in the API
# can ever finish or discard it.
sweep_gate_residue() {
    api_exec python - <<PYEOF 2>/dev/null || true
import os
import psycopg2

TICKET = "${GATE_SEED_TICKET_ID}"

conn = psycopg2.connect(
    host=os.environ["DB_HOST"], port=os.environ["DB_PORT"],
    dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"])
conn.autocommit = True
cur = conn.cursor()
cur.execute("""
DELETE FROM uploads_sessions
 WHERE parent_tab = 'maintenances'
   AND NOT EXISTS (SELECT 1 FROM maintenances m
                    WHERE m.maintenance_id = uploads_sessions.parent_id)
""")
sessions = cur.rowcount

cur.execute("DELETE FROM photos WHERE photo_path LIKE %s", ("%/" + TICKET + "/%",))
photos = cur.rowcount

print(sessions + photos)
PYEOF
}

preflight_cleanup() {
    # `python -` on purpose: psql is not in the runtime image, and psycopg2 is the
    # driver's own library, so this needs nothing the container lacks.
    local removed
    removed="$(api_exec python - <<PYEOF 2>/dev/null || true
import os
import psycopg2

conn = psycopg2.connect(
    host=os.environ["DB_HOST"], port=os.environ["DB_PORT"],
    dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"])
conn.autocommit = True
cur = conn.cursor()

cur.execute("DELETE FROM maintenances WHERE ticket_id = %s", ("${GATE_SEED_TICKET_ID}",))
maintenances = cur.rowcount

cur.execute("DELETE FROM tickets WHERE ticket_id = %s", ("${GATE_SEED_TICKET_ID}",))
tickets = cur.rowcount

print("%d %d" % (maintenances, tickets))
PYEOF
)"
    local orphans
    orphans="$(sweep_gate_residue)"

    if [ -z "$removed" ] && [ -z "$orphans" ]; then
        warn "could not run the preflight sweep; a previous failed run may have left rows behind"
        return 0
    fi
    if [ "${removed:-0 0}" != "0 0" ] || [ "${orphans:-0}" != "0" ]; then
        dim "preflight removed leftovers from an earlier run (${orphans:-?} orphan sessions, ${removed:-?} maintenances/tickets)"
    fi
}

# ── 10.2 the precondition, before anything is written ───────────────────────
# A verification step that writes is only safe if it is certain which database and
# which bucket it is writing to. On a shared core a wrong name is not an
# inconvenience: it is a write into another project's tenant, performed by a
# command whose entire purpose was to check this one. So this runs first, reads
# only, and on mismatch writes nothing, uploads nothing, and reports BOTH names.
verify_targets() {
    step "Targeting (nothing is written until this passes)"

    local resolved_db expected_db resolved_bucket expected_bucket api_id

    api_id="$(api_container_id || true)"
    if [ -z "$api_id" ]; then
        die "no running api container found for this compose project.
  compose file  ${COMPOSE_FILE}
  project       ${COMPOSE_PROJECT_NAME}

  Is the local stack up? Run: make setup-local"
    fi

    resolved_db="$(container_env "$api_id" DB_NAME || true)"
    expected_db="$DB_NAME"
    resolved_bucket="$(container_env "$api_id" MINIO_DEFAULT_BUCKET || true)"
    expected_bucket="$MINIO_DEFAULT_BUCKET"

    if [ "$resolved_db" != "$expected_db" ]; then
        die "$(cat <<EOF
the running API is connected to a DIFFERENT database than this project expects.

  resolved (from the container)   ${resolved_db:-<unset>}
  expected   (from .env)          ${expected_db}

Refusing to continue. Every check below creates a ticket and uploads an object, and
a write to the wrong database here is a write into another project's tenant.
EOF
)"
    fi
    pass "database is ${resolved_db}"

    if [ "$resolved_bucket" != "$expected_bucket" ]; then
        die "$(cat <<EOF
the running API is pointed at a DIFFERENT bucket than this project expects.

  resolved (from the container)   ${resolved_bucket:-<unset>}
  expected   (from .env)          ${expected_bucket}

Refusing to continue. The storage check uploads and deletes an object, and the
object store is shared.
EOF
)"
    fi
    pass "bucket is ${resolved_bucket}"

    CREATED_BUCKET="$resolved_bucket"
}

# ── 10.4 / 10.5 the image that is actually running ──────────────────────────
verify_image() {
    step "Image"

    # Read from the container's configuration, not from the Dockerfile text: the
    # Dockerfile states an intention, the container reports what is true.
    local user
    user="$(docker inspect --format '{{.Config.User}}' "$(docker compose -f "$COMPOSE_FILE" ps -q api)" 2>/dev/null || true)"
    case "$user" in
        ""|root|0|"0:0")
            die "the API container runs as '${user:-<unset>}' — root is not an acceptable default for a service holding database and object-store credentials."
            ;;
    esac
    pass "container user is '${user}', not root"

    # Both are used by nothing under app/. pytest and pandas reached the shipped
    # image because development dependencies were installed into it; the split into
    # requirements.txt / requirements-dev.txt is what removes them.
    local module
    for module in pytest pandas; do
        if api_exec python -c "import ${module}" >/dev/null 2>&1; then
            die "'${module}' is importable inside the shipped image. It is a development dependency, used by nothing under app/, and its presence means a production dependency set cannot be reasoned about from this image."
        fi
        pass "${module} is not importable in the image"
    done
}

# ── 10.6 authenticated read ─────────────────────────────────────────────────
# The cheapest authenticated read in the app, chosen because it exercises the
# token-blacklist query and the user fetch. A wrong JWT_SECRET, a missing
# token_blacklist table, or a role that cannot read fsm_users all fail here.
verify_authenticated_read() {
    step "Authenticated read"

    local login me_status
    login="$(curl -sS -X POST "${API_BASE}/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"${SEED_USER_EMAIL}\",\"password\":\"${SEED_USER_PASSWORD}\"}" || true)"

    # TOKEN, not a local `token`: the later checks are separate functions and a
    # function-local is invisible to them, so `${TOKEN}` raised
    # "token: unbound variable" under `set -u` the moment the first write ran.
    TOKEN="$(printf '%s' "$login" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || true)"
    [ -n "$TOKEN" ] || die "POST /auth/login did not return a token: ${login}

The gate needs an account that exists in this project's database. ${DB_NAME} is
provisioned by 'make setup-local', but nothing seeds a user — recorded as
tasks.md §10.6. The account is created by 'make setup-local' from
SEED_USER_EMAIL/SEED_USER_PASSWORD in .env; check those."
    pass "POST /auth/login returned a token"

    me_status="$(curl -sS -o /tmp/gate-local-me.json -w '%{http_code}' \
        -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/auth/me" || true)"
    [ "$me_status" = "200" ] || die "GET /auth/me returned ${me_status}, expected 200. Body: $(cat /tmp/gate-local-me.json 2>/dev/null)"
    pass "GET /auth/me returned 200"
}

# ── 10.7 write, then remove it ──────────────────────────────────────────────
verify_write() {
    step "Write and delete"

    # `priority` and `status` are PostgreSQL enums, not free text: the labels are
    # LOW/MEDIUM/HIGH and OPEN/ASSIGNED/CANCELLED/... Sending lowercase -- which is
    # what this did first -- reaches the database and fails there with
    # `invalid input value for enum priority_type: "low"`, surfacing as a 500 whose
    # cause is a string in a test fixture.
    local response ticket_id
    response="$(curl -sS -X POST "${API_BASE}/tickets" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "$(cat <<JSON
{"ticket_id":${GATE_SEED_TICKET_ID},"ticket_date":"$(date -u +%F)","ticket_description":"${GATE_TICKET_DESCRIPTION}","priority":"LOW","status":"OPEN","market_id":${GATE_SEED_MARKET_ID},"equipment_id":${GATE_SEED_EQUIPMENT_ID}}
JSON
)" || true)"

    ticket_id="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ticket_id",""))' 2>/dev/null || true)"
    [ -n "$ticket_id" ] || die "POST /tickets did not return a ticket: ${response}"
    CREATED_TICKET_ID="$ticket_id"
    pass "POST /tickets created ticket ${ticket_id}"

    # NOT deleted here. This ticket is the upload's parent: `POST /uploads/complete`
    # loads the parent row and 404s when it is absent
    # (app/services/upload_service.py:172 -- "maintenances ... no longer exists").
    # A fixed UUID with no row behind it satisfies `init`, which persists the
    # session without checking, and then fails at `complete`. Using a real ticket
    # also means one write instead of two. `verify_delete` removes it at the end.
}

# Creates the maintenance that owns the upload. Done through the API rather than
# by inserting a row directly, so the id is one the application itself produced
# (a UUID7) and the write path is exercised instead of bypassed.
verify_maintenance() {
    step "Maintenance"

    local response maintenance_id
    response="$(curl -sS -X POST "${API_BASE}/maintenances" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "{\"ticket_id\":${CREATED_TICKET_ID},\"maintenance_date\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" || true)"

    maintenance_id="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("maintenance_id",""))' 2>/dev/null || true)"
    [ -n "$maintenance_id" ] || die "POST /maintenances did not return a maintenance_id: ${response}"
    CREATED_MAINTENANCE_ID="$maintenance_id"
    pass "POST /maintenances created maintenance ${maintenance_id}"
}

# The delete, as its own step, after the upload has used the maintenance.
verify_delete() {
    step "Delete"

    # Maintenance first: it is the upload's parent and references the ticket.
    local deleted maintenance_gone
    deleted="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/maintenances/${CREATED_MAINTENANCE_ID}" || true)"
    [ "$deleted" = "204" ] || die "DELETE /maintenances/${CREATED_MAINTENANCE_ID} returned ${deleted}, expected 204. The gate's cleanup failed and the database is left with a test row."
    maintenance_gone="$(curl -sS -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/maintenances/${CREATED_MAINTENANCE_ID}" || true)"
    [ "$maintenance_gone" = "404" ] || die "GET /maintenances/${CREATED_MAINTENANCE_ID} returned ${maintenance_gone} after deletion, expected 404. The row may still exist."
    pass "DELETE /maintenances/${CREATED_MAINTENANCE_ID} returned 204 and is gone"
    CREATED_MAINTENANCE_ID=""

    deleted="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/tickets/${CREATED_TICKET_ID}" || true)"
    [ "$deleted" = "204" ] || die "DELETE /tickets/${CREATED_TICKET_ID} returned ${deleted}, expected 204. The gate's cleanup failed and the database is left with a test row."
    pass "DELETE /tickets/${CREATED_TICKET_ID} returned 204"

    # Confirm it is really gone rather than trusting the status code.
    local after
    after="$(curl -sS -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/tickets/${CREATED_TICKET_ID}" || true)"
    [ "$after" = "404" ] || die "GET /tickets/${CREATED_TICKET_ID} returned ${after} after deletion, expected 404. The row may still exist."
    pass "GET /tickets/${CREATED_TICKET_ID} returns 404"
    CREATED_TICKET_ID=""
}

# ── 10.8 storage round trip, and the only check that reaches the object store ──
# This is the check that catches an exhausted connection pool, a missing
# migration, or wrong object-store credentials — none of which any other check
# here can see, because a health endpoint and a health check both stop before the
# dependency. It also runs through the application's own upload service, so a
# presigned URL built with the wrong public origin fails here rather than on a
# client's device.
verify_storage() {
    step "Storage round trip"

    local payload expected_sha upload_id chunk_size total_chunks
    payload="gate-local payload: deterministic bytes for a byte-for-byte comparison"
    expected_sha="$(printf '%s' "$payload" | sha256sum | cut -d' ' -f1)"
    total_size="$(printf '%s' "$payload" | wc -c | tr -d ' ')"

    local init
    init="$(curl -sS -X POST "${API_BASE}/uploads/init" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "{\"parent_tab\":\"${GATE_PARENT_TAB}\",\"parent_id\":\"${CREATED_MAINTENANCE_ID}\",\"tab_name\":\"photos\",\"col_name\":\"photo_file\",\"content_type\":\"application/pdf\",\"total_size\":${total_size},\"total_chunks\":1}" || true)"
    upload_id="$(printf '%s' "$init" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("upload_id",""))' 2>/dev/null || true)"
    [ -n "$upload_id" ] || die "POST /uploads/init did not return an upload_id: ${init}"
    chunk_size="$(printf '%s' "$init" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("chunk_size",0))' 2>/dev/null || echo 0)"
    pass "POST /uploads/init created session ${upload_id} (chunk_size ${chunk_size})"

    # A chunk smaller than chunk_size is the final chunk and completes the upload.
    if [ "$total_size" -gt "$chunk_size" ]; then
        dim "payload exceeds one chunk; the gate sends a single chunk by construction"
    fi

    printf '%s' "$payload" > /tmp/gate-local-payload.bin
    local chunk
    chunk="$(curl -sS -X POST "${API_BASE}/uploads/chunk?upload_id=${upload_id}&chunk_index=0" \
        -H "Authorization: Bearer ${TOKEN}" \
        -F "chunk=@/tmp/gate-local-payload.bin;type=application/pdf" || true)"
    printf '%s' "$chunk" | grep -q 'received_chunks' \
        || die "POST /uploads/chunk was not accepted: ${chunk}"
    pass "POST /uploads/chunk accepted chunk 0"

    local completed file_url
    completed="$(curl -sS -X POST "${API_BASE}/uploads/complete?upload_id=${upload_id}" \
        -H "Authorization: Bearer ${TOKEN}" || true)"
    file_url="$(printf '%s' "$completed" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("file_url") or "")' 2>/dev/null || true)"
    [ -n "$file_url" ] || die "POST /uploads/complete returned no file_url: ${completed}"
    pass "POST /uploads/complete produced a presigned URL"

    # The URL's host must be the PUBLIC origin, because it is handed to a mobile
    # client on a different network. MINIO_ENDPOINT is the in-cluster name, which
    # resolves nowhere outside this project's network — a URL pointing at it fails
    # on the device while working perfectly here.
    local url_host expected_host
    url_host="$(printf '%s' "$file_url" | sed -E 's#^[a-zA-Z]+://([^/:]+).*#\1#')"
    expected_host="${MINIO_PUBLIC_ENDPOINT}"
    if [ "$url_host" != "$expected_host" ]; then
        die "$(cat <<EOF
the presigned URL points at '${url_host}', not the public origin '${expected_host}'.

  MINIO_ENDPOINT          ${MINIO_ENDPOINT}      (in-network name; not resolvable by a client)
  MINIO_PUBLIC_ENDPOINT   ${MINIO_PUBLIC_ENDPOINT}      (what a client must be given)

A URL built with the internal origin works here and fails on every device.
EOF
)"
    fi
    # The two origins differ only when the internal one is unresolvable to a
    # client -- the VPS case, where MINIO_ENDPOINT is a compose service name on a
    # private network and the public origin is a domain. On a developer machine
    # MinIO is published on loopback and a client genuinely can resolve it, so
    # MINIO_PUBLIC_ENDPOINT is legitimately the same string as MINIO_ENDPOINT.
    # Asserting they differ unconditionally rejected a correct configuration; the
    # defect it was written to catch is the URL naming a private-network name.
    if [ "$expected_host" != "$MINIO_ENDPOINT" ]; then
        [ "$url_host" != "$MINIO_ENDPOINT" ] || die "the presigned URL host equals MINIO_ENDPOINT (${MINIO_ENDPOINT}); it must be the public origin"
        pass "presigned URL host is not MINIO_ENDPOINT (${MINIO_ENDPOINT})"
    else
        pass "public origin is loopback (${expected_host}), the same origin a client uses locally"
    fi

    # Fetched from inside the container, so the bytes travel the same path a
    # client takes rather than the host's loopback mapping. This probe is allowed
    # to fail: the container reaches the object store by its in-network name, so
    # a presigned URL naming the public origin is unreachable from inside it.
    # That is the case the host fallback below exists for, and its traceback is
    # expected output here rather than a defect, so stderr is discarded instead of
    # printing a stack trace into output that gets pasted into a release note.
    local downloaded
    downloaded="$(api_exec python -c "
import hashlib, sys, urllib.request
with urllib.request.urlopen('${file_url}', timeout=15) as response:
    sys.stdout.write(hashlib.sha256(response.read()).hexdigest())
" 2>/dev/null || true)"
    if [ "$downloaded" != "$expected_sha" ]; then
        dim "in-container fetch did not match; trying from the host"
        downloaded="$(curl -sS "${file_url}" | sha256sum | cut -d' ' -f1)"
    fi
    [ "$downloaded" = "$expected_sha" ] \
        || die "the bytes read back do not match what was sent.
  sent     ${expected_sha}
  received ${downloaded}
The object store accepted the upload and returned different content."
    pass "presigned GET returned byte-identical content (sha256 ${expected_sha:0:12}…)"

    # The object KEY, not the URL. remove_object() hands this to
# `client.remove_object(bucket, key)`, which wants the bucket-relative path with
# no scheme, host or query string. Keeping the presigned URL here made the
# removal fail every time -- and it failed the way a leak does: a warning, not an
# error, so every run left one more object in the bucket, in a path named after
# the ticket the same gate had already deleted.
    local object_path
    object_path="${file_url#*://*/}"      # drop scheme and host
    object_path="${object_path#*/}"       # drop the bucket segment
    object_path="${object_path%%\?*}"    # drop the signature query string
    [ -n "$object_path" ] || die "could not derive the object key from ${file_url}"
    CREATED_OBJECT_KEY="$object_path"
    remove_object
}

# The application exposes no route that deletes an uploaded object, so cleanup
# uses the MinIO client with the application's own credentials — the same client
# app/core/storage.py builds. This is deletion, not verification: the check above
# deliberately read the bytes back through the application's presigned URL.
# Recorded as a follow-up in tasks.md §10.8.
remove_object() {
    [ -n "$CREATED_OBJECT_KEY" ] || return 0
    api_exec python -c "
import os
from minio import Minio
client = Minio(os.environ['MINIO_ENDPOINT'] + ':' + os.environ['MINIO_PORT'],
               access_key=os.environ['MINIO_ACCESS_KEY'],
               secret_key=os.environ['MINIO_SECRET_KEY'],
               secure=os.environ['MINIO_SECURE'] == 'true')
client.remove_object(os.environ['MINIO_DEFAULT_BUCKET'], '${CREATED_OBJECT_KEY}')
print('removed ${CREATED_OBJECT_KEY}')
" >/dev/null 2>&1 || warn "could not remove the test object ${CREATED_OBJECT_KEY} from ${CREATED_BUCKET}; remove it by hand"
    CREATED_OBJECT_KEY=""
}

# ── 10.11 the pasteable block ───────────────────────────────────────────────
# Printed on success and on failure, so a pasted release note carries the state
# the checks actually ran against and not just the word "passed".
print_summary() {
    local outcome="${1:-}"
    local image_id revision
    image_id="$(docker image inspect --format '{{.Id}}' "$API_IMAGE" 2>/dev/null | cut -c1-19 || echo unknown)"

    # Read through the app's own migration path rather than `psql`: §10.14 forbids
    # standing a database client in for the application, and the revision the
    # application believes in is the one worth reporting.
    # shellcheck source=infra/local/scripts/lib-migrate.sh
    . "${SCRIPT_DIR}/lib-migrate.sh"
    migrate_env_args "$COMPOSE_FILE" "$CORE_DB_ADMIN_USER" "$CORE_DB_ADMIN_PASSWORD"
    revision="$(alembic_current_revision "$COMPOSE_FILE" || true)"

    printf '\n%s────────────────────────────────────────────────────────%s\n' "$BOLD" "$RESET"
    printf '%sgate-local%s  %s%s%s\n' "$BOLD" "$RESET" "$BOLD" "${outcome:-incomplete}" "$RESET"
    printf '%s────────────────────────────────────────────────────────%s\n' "$BOLD" "$RESET"
    printf '  %-24s %s\n' "image" "$API_IMAGE @ ${image_id}"
    printf '  %-24s %s\n' "database" "${DB_NAME} @ ${revision:-unknown revision}"
    printf '  %-24s %s\n' "bucket" "${MINIO_DEFAULT_BUCKET}"
    printf '  %-24s %s\n' "object store (internal)" "${MINIO_ENDPOINT}:${MINIO_PORT} secure=${MINIO_SECURE}"
    printf '  %-24s %s\n' "object store (public)" "${MINIO_PUBLIC_ENDPOINT}:${MINIO_PUBLIC_PORT} secure=${MINIO_PUBLIC_SECURE}"
    printf '\n  %s\n' "checks"
    local entry name result
    for entry in "${RESULTS[@]}"; do
        name="${entry%|*}"; result="${entry#*|}"
        case "$result" in
            pass) printf '    %s✓%s %s\n' "$GREEN" "$RESET" "$name" ;;
            warn) printf '    %s!%s %s\n' "$YELLOW" "$RESET" "$name" ;;
            *)    printf '    %s✗%s %s\n' "$RED" "$RESET" "$name" ;;
        esac
    done

    cat <<'LIMITS'

  limits of this result — read before quoting it as evidence

  * A local check is not a staging environment. It does not exercise the VPS
    network, its TLS origin, or its scheduling.
  * Local now reaches the shared core exactly as the VPS does — same container
    names, same in-network DNS — so a pass is stronger evidence of CONFIGURATION
    correctness than a local setup that had to work around the core. It is not
    evidence of DEPLOYMENT correctness. The gates that cover deployment-specific
    behaviour are docs/deployment-guide.md §5.4 (health) and §5.5 (media
    round-trip).
  * This gate exercises THIS PROJECT's access to the core. It does not check the
    core's own health, backup, patching or availability. A defect in the core's
    declaration appears here as a connection failure and is owned by the project
    that operates it.

LIMITS
}

# ── main ────────────────────────────────────────────────────────────────────
main() {
    load_env

    # Same reason as in setup.sh: the gate addresses containers by compose project,
    # so this project must never be reachable under another project's namespace.
    # COMPOSE_PROJECT_NAME is also reserved in load_env below.
    COMPOSE_PROJECT_NAME="app-tickets-local"
    export COMPOSE_PROJECT_NAME

    API_IMAGE="$(awk '/^  api:/{s=1} s && /^    image:/{print $2; exit}' "$COMPOSE_FILE")"
    [ -n "$API_IMAGE" ] || die "could not read the api image tag from ${COMPOSE_FILE}"

    require_env \
        DB_NAME \
        MINIO_ENDPOINT MINIO_PORT MINIO_SECURE MINIO_DEFAULT_BUCKET \
        MINIO_ACCESS_KEY MINIO_SECRET_KEY \
        MINIO_PUBLIC_ENDPOINT MINIO_PUBLIC_PORT MINIO_PUBLIC_SECURE \
        SEED_USER_EMAIL SEED_USER_PASSWORD \
        GATE_SEED_TICKET_ID GATE_SEED_MARKET_ID GATE_SEED_EQUIPMENT_ID \
        CORE_DB_ADMIN_USER CORE_DB_ADMIN_PASSWORD

    # The published port comes from compose rather than a guess, because the gate
    # talks to the container the same way a developer does.
    local published
    published="$(docker compose -f "$COMPOSE_FILE" port api 8000 2>/dev/null | head -1 || true)"
    [ -n "$published" ] || die "the api service is not running. Run make setup-local first."
    API_BASE="http://${published}"
    TOKEN=""

    preflight_cleanup
    verify_targets
    verify_image
    verify_authenticated_read
    verify_write
    verify_maintenance
    verify_storage
    verify_delete

    # A passing gate must leave the database and the bucket as it found them. The
    # session row outlives its maintenance -- nothing in the API deletes it -- so
    # it is swept here, after the parent is gone and the row is therefore an
    # orphan, using exactly the rule the preflight uses.
    sweep_gate_residue >/dev/null

    trap - EXIT
    print_summary passed
}

main "$@"
