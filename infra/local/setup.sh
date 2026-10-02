#!/usr/bin/env bash
#
# `make setup-local` — bring this project to a working environment in one command.
#
# WHAT THIS SCRIPT OWNS
#   This project's containers, this project's database, bucket, object-store user
#   and credentials, and one network: app-tickets-local-net.
#
# WHAT THIS SCRIPT DOES NOT OWN, AND NEVER TOUCHES
#   The shared core: postgres-gci and minio-acme. Their lifecycle belongs to the
#   project that operates them. There is no `docker start`, `docker stop`,
#   `docker restart` or `docker rm` against them anywhere in this file, in either
#   direction. `bootstrap.sh:79` (`docker start postgres-gci`) is the pattern to
#   avoid: starting what is not ours couples us to its lifecycle, and stopping
#   what is not ours is an outage for every other project on that database.
#
#   The only mutation this script performs against a container it does not declare
#   is `docker network connect` / `docker network disconnect`, scoped to the
#   network this stack owns. `tests/test_local_assets.py` enforces both rules.
#
# WHY THE CONNECT IS REPEATED RATHER THAN DONE ONCE
#   The attachment lives INSIDE the container, so a recreate performed by the
#   core's own project erases it: no log line, no error, and the API then fails on
#   its first request while its healthcheck still passes. Idempotent re-running
#   is the mitigation, not the fix — the durable remedy is for the core's own
#   compose to declare this network `external: true` on its services, which is a
#   file we must not edit (raised as tasks.md §17.16). So the connect runs on
#   every bring-up, and reports what it made.
#
# WHERE THE CORE LIVES
#   Nowhere in this repository, and never as a hardcoded path. The location comes
#   from CORE_COMPOSE_COMMAND in .env, recorded at tasks.md §6.7. If that key is
#   unset this script stops and says so by name, rather than falling back to a
#   path that happens to exist on the machine that wrote it.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/infra/local/docker-compose.yml"
ENV_FILE="${PROJECT_ROOT}/.env"

# Container names as declared by the core's own compose. They are external
# identities, not services this repository declares, which is why they appear as
# constants here and not in infra/local/docker-compose.yml. Pinned against the
# declarations at tasks.md §6.11.
CORE_PG_CONTAINER="postgres-gci"
CORE_MINIO_CONTAINER="minio-acme"

# How long to wait for a dependency to answer a real query. A container that is
# "Up" is not a database that accepts connections; the recorded failure mode is an
# application that starts cleanly and then fails on first use.
READY_TIMEOUT_SECONDS=90

SKIP_BUILD=0
# Names this script owns. `load_env` refuses to let `.env` define them; see the
# guard in that function for why an ordinary-looking key in `.env` can otherwise
# move every path the script reads.
RESERVED_KEYS="COMPOSE_PROJECT_NAME SCRIPT_DIR PROJECT_ROOT COMPOSE_FILE ENV_FILE API_IMAGE MIGRATE_IMAGE LOCAL_NETWORK EXPECTED_NETWORK CORE_PG_CONTAINER CORE_MINIO_CONTAINER READY_TIMEOUT_SECONDS SKIP_BUILD TMP_WORKDIR PROVISION_SQL PROVISION_RUNTIME SCHEMA_SEED_MARKER"
# Resolved from the compose file, not hardcoded. A previous version hardcoded
# `app-tickets-backend:api-local`, which compose never builds, so every probe that
# used it failed with "pull access denied" -- and because the probe discarded its
# output, the operator was told the object store was unhealthy when nothing had
# even been asked of it. Derived, a rename cannot drift; hardcoded, it can.
API_IMAGE=""
MIGRATE_IMAGE=""

# ── output ───────────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
    YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
    BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; RESET=""
fi

step() { printf '\n%s==>%s %s%s%s\n' "$BOLD" "$RESET" "$BOLD" "$1" "$RESET"; }
info() { printf '    %s\n' "$1"; }
dim()  { printf '    %s%s%s\n' "$DIM" "$1" "$RESET"; }
ok()   { printf '    %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '    %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
die()  { printf '\n%sERROR:%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: make setup-local [--skip-build]

Brings this project to a working environment against an already-running shared
core (postgres-gci and minio-acme).

  --skip-build   Reuse existing images instead of rebuilding them.
  -h, --help     Show this message.

Required in .env (see .env.example):
  CORE_COMPOSE_COMMAND    where the core's own compose lives — owned elsewhere
  CORE_DB_ADMIN_USER      the core's administrative credential — owned elsewhere
  CORE_DB_ADMIN_PASSWORD  the core's administrative credential — owned elsewhere
  CORE_MINIO_ROOT_USER    the core's administrative credential — owned elsewhere
  CORE_MINIO_ROOT_PASSWORD the core's administrative credential — owned elsewhere
  DB_NAME DB_USER DB_PASSWORD ... this project's own settings
  SEED_USER_EMAIL SEED_USER_PASSWORD  the local account `make gate-local` logs in with

This script never starts, stops, restarts or removes the core's containers.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-build) SKIP_BUILD=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown argument: $1" ;;
    esac
done

# ── .env ─────────────────────────────────────────────────────────────────────
# Loaded rather than `source`d: .env is data, and sourcing it would execute
# whatever is in it. Inline comments are stripped because docker compose does not
# strip them either, so a line copied from .env.example must behave identically
# here and there.
load_env() {
    [ -f "$ENV_FILE" ] || die ".env is missing. Copy .env.example to .env and fill it in: cp .env.example .env"

    local line key value
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'#'*) continue ;;
            *=*) ;;
            *) continue ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        # Strip an unquoted trailing comment, matching docker compose.
        case "$value" in
            \"*\") value="${value%\"*}"; value="${value#\"}" ;;
            \'*\') value="${value%\'*}"; value="${value#\'}" ;;
            *)     value="${value%%#*}"; value="${value%"${value##*[![:space:]]}"}" ;;
        esac
        key="${key%"${key##*[![:space:]]}"}"
        case "$key" in
            [A-Za-z_]*) ;;
            *) continue ;;
        esac
        # `.env` may not define this script's own structural variables. `load_env`
        # assigns every key it reads, so a `.env` carrying a generic name like
        # PROJECT_ROOT silently redirected every repo-relative path -- schema,
        # provisioning template, seed directory -- into whatever that value said.
        # The failure is silent and the paths are read far from the assignment, so
        # a developer's .env must not be able to move them at all.
        case " $RESERVED_KEYS " in
            *" ${key} "*) warn ".env defines ${key}, which this script owns; ignoring it" ; continue ;;
        esac
        printf -v "$key" '%s' "$value"
        export "$key"
    done < "$ENV_FILE"
}

require_env() {
    local key value
    for key in "$@"; do
        value="${!key:-}"
        if [ -z "$value" ]; then
            case "$key" in
                CORE_*)
                    die "$(cat <<EOF
$key is not set in .env.

  dependency   the shared core (${CORE_PG_CONTAINER}, ${CORE_MINIO_CONTAINER})
  owner        the project that operates the core — not this repository
  what to do   set $key in .env to that project's documented location/credential

This repository will not guess it and will not fall back to a path from the
machine where .env.example was written. A connection error from the application
would hide the real cause; this message names it.
EOF
)" ;;
                *)
                    die "$key is not set in .env. See .env.example for this project's own settings." ;;
            esac
        fi
    done
}

# ── the core: resolved, then confirmed running, then attached ────────────────
# Order matters and is enforced by tests/test_local_assets.py: a running-state
# check must appear before any `docker network connect`. Connecting to a stopped
# container is at best a no-op and at worst an error that gets mistaken for
# "the core is broken" when in fact it is simply not started, which is not ours
# to fix.
core_running_state() {
    docker inspect --format '{{.State.Status}}' "$1" 2>/dev/null || printf 'absent'
}

assert_core_running() {
    local container state
    for container in "$CORE_PG_CONTAINER" "$CORE_MINIO_CONTAINER"; do
        state="$(core_running_state "$container")"
        if [ "$state" = "absent" ]; then
            die "$(cat <<EOF
container ${container} does not exist on this machine.

  dependency   the shared core
  owner        the project that operates the core — not this repository
  what to do   start the core from that project, on the machine where it runs

This script will not create it. A core that is missing and a core that is merely
stopped are different problems, and this one is not ours to solve.
EOF
)"
        fi
        # An unhealthy container is still running, and connecting to it would
        # hide a real fault behind a successful attach. Report it and stop.
        if [ "$state" != "running" ]; then
            die "$(cat <<EOF
container ${container} is not running — docker inspect reports state: ${state}.

  dependency   the shared core
  owner        the project that operates the core — not this repository
  what to do   start or repair it from that project, then re-run this command

This script will not start it. Starting a shared dependency couples this
repository to another project's lifecycle, and a start that fails half-way is an
outage for every other tenant on that database.
EOF
)"
        fi
        ok "${container} is running"
    done
}

network_exists() {
    docker network inspect "$1" >/dev/null 2>&1
}

container_on_network() {
    docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' \
        "$1" 2>/dev/null | tr ' ' '\n' | grep -Fxq "$2"
}

connect_core_to_local_network() {
    local container outcome
    for container in "$CORE_PG_CONTAINER" "$CORE_MINIO_CONTAINER"; do
        if container_on_network "$container" "$LOCAL_NETWORK"; then
            ok "${container} was already attached to ${LOCAL_NETWORK}"
        else
            # The network is named literally on this line on purpose. It is the one
            # command in this file that changes another project's container, so which
            # network it changes must be readable from the command itself — not
            # inferred from a variable. main() proves the literal below matches what
            # infra/local/docker-compose.yml declares, so the two cannot drift apart
            # without setup failing loudly.
            docker network connect app-tickets-local-net "$container"
            ok "${container} attached to ${LOCAL_NETWORK} (newly attached)"
        fi
        outcome="$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' \
            "$container" | tr ' ' '\n' | grep -Fx "$LOCAL_NETWORK" || true)"
        [ -n "$outcome" ] || die "${container} is not attached to ${LOCAL_NETWORK} after connecting it"
    done
}

# ── readiness: a real query, never a container state ─────────────────────────
wait_for_postgres() {
    local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
    while [ "$SECONDS" -lt "$deadline" ]; do
        if docker exec "$CORE_PG_CONTAINER" pg_isready -q -U "$CORE_DB_ADMIN_USER" -d postgres >/dev/null 2>&1; then
            return 0
        fi
        dim "waiting for ${CORE_PG_CONTAINER} to accept connections..."
        sleep 2
    done
    die "$(cat <<EOF
${CORE_PG_CONTAINER} is running but did not accept a connection within ${READY_TIMEOUT_SECONDS}s.

  This is not a network problem — the container answered docker inspect. It is the
  database inside it that is not ready, which belongs to the core's owner to
  diagnose. This script will not restart it.
EOF
)"
}

wait_for_minio() {
    local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
    while [ "$SECONDS" -lt "$deadline" ]; do
        # Probed from inside this project's own network by our own image, so the
        # check proves the path the application will actually use — name
        # resolution across the network plus reachability — instead of the host's
        # loopback mapping, which the container never uses.
        if docker run --rm --network "$LOCAL_NETWORK" --entrypoint python "$API_IMAGE" -c "
import sys, urllib.request
try:
    urllib.request.urlopen('http://${CORE_MINIO_CONTAINER}:9000/minio/health/live', timeout=3)
except Exception as exc:
    sys.exit(1)
" >/dev/null 2>&1; then
            return 0
        fi
        dim "waiting for ${CORE_MINIO_CONTAINER} to answer its health endpoint..."
        sleep 2
    done
    die "$(cat <<EOF
${CORE_MINIO_CONTAINER} is attached to ${LOCAL_NETWORK} but did not answer its health
endpoint within ${READY_TIMEOUT_SECONDS}s from inside that network.

  Resolution and reachability have both been tested, so this is the object store
  itself, which belongs to the core's owner. This script will not restart it.
EOF
)"
}

# ── provisioning: idempotent, and ours ───────────────────────────────────────
psql_admin() {
    docker exec -i "$CORE_PG_CONTAINER" psql -v ON_ERROR_STOP=1 -q -U "$CORE_DB_ADMIN_USER" -d postgres "$@"
}

psql_app_db() {
    docker exec -i "$CORE_PG_CONTAINER" psql -v ON_ERROR_STOP=1 -q -U "$CORE_DB_ADMIN_USER" -d "$DB_NAME" "$@"
}

role_exists() {
    [ "$(psql_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}'" | tr -d '[:space:]')" = "1" ]
}

database_exists() {
    [ "$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | tr -d '[:space:]')" = "1" ]
}

# Creating the database is a separate step from granting on it, because the two
# have to happen either side of the schema. The canonical template names tables
# explicitly (`GRANT SELECT, INSERT, UPDATE, DELETE ON adticketswkd, ...`), so it
# needs them to exist; and migration 0001 creates token_blacklist, so it has to run
# after `alembic upgrade head` as well. This function is the "before"; the template
# is the "after"; the schema and the migrations are what sit between them.
#
# Running the template against a freshly created, still empty database is what the
# first version did, and it failed on `relation "adticketswkd" does not exist` --
# after CREATE ROLE had already taken effect, leaving a half-applied role the next
# run reported as "already exists". It only ever passed on a machine where the
# database happened to be populated already.
ensure_database() {
    if database_exists; then
        ok "database ${DB_NAME} already exists"
    else
        psql_admin -c "CREATE DATABASE \"${DB_NAME}\"" >/dev/null
        ok "database ${DB_NAME} created"
    fi
}

provision_database() {
    local template="${PROJECT_ROOT}/infra/provision/001-create-application-roles.sql"
    PROVISION_SQL="${TMP_WORKDIR}/provision-role.sql"

    # The template states the division of labour itself: "No CREATE DATABASE. The
    # database is created empty, by an administrator." ensure_database() is that
    # administrator step, and it has already run.
    database_exists || die "${DB_NAME} does not exist. ensure_database must run before the template."

    # The grants are applied EVERY time, not only when the role is absent.
    #
    # Roles are cluster-wide; grants live inside a database. So a database dropped
    # and recreated keeps the role and loses every grant it had. A previous version
    # skipped the whole template whenever the role existed, so exactly that
    # sequence -- drop the database, bring it up again -- produced an application
    # role with no privileges at all, and the failure surfaced much later as
    # "permission denied for table fsm_users": a 500 on login, several steps
    # removed from the cause. Everything in the template except CREATE ROLE is
    # idempotent, so the template is re-applied and only CREATE ROLE is dropped.
    ROLE_ALREADY_EXISTS=0
    if role_exists; then
        ROLE_ALREADY_EXISTS=1
    fi

    # `<runtime>` is the PREFIX, not the role name: the canonical template is
    # `CREATE ROLE <runtime>_app`, and it is a no-touch file shared with the VPS,
    # so the suffix cannot be dropped to suit this script. Substituting the full
    # DB_USER here would create `gestiket_app_app` while `role_exists` looks for
    # `gestiket_app`, and the mismatch would only surface as a login failure.
    PROVISION_RUNTIME="${DB_USER%_app}"

    # The template quotes the password placeholder itself -- PASSWORD
    # '<generated-password>' -- so a single quote in the password has to be
    # doubled to stay inside the SQL literal. An unescaped quote would end the
    # literal and turn the rest of the password into SQL.
    role_password_sql="${DB_PASSWORD//\'/\'\'}"
    # sed's own replacement metacharacters are escaped separately, so a
    # password containing \ or & cannot alter what the substitution means.
    role_password_sed="${role_password_sql//\\/\\\\}"
    role_password_sed="${role_password_sed//&/\\&}"

    # Only the executable lines are substituted. The file's comment blocks
    # carry documentation examples with their own placeholders, and rewriting
    # those would turn the documentation into false statements.
    sed -e 's|<runtime>|'"${PROVISION_RUNTIME}"'|g' \
        -e 's|<database>|'"${DB_NAME}"'|g' \
        -e 's|<admin>|'"${CORE_DB_ADMIN_USER}"'|g' \
        -e 's|<generated-password>|'"${role_password_sed}"'|g' "$template" \
        | grep -vE '^[[:space:]]*--' \
        | sed -e '/./,$!d' > "$PROVISION_SQL"

    # The substituted prefix and the role this script connects as must be the
    # same string. Checked, not assumed: a role created under one name and used
    # under another produces a confusing authentication error much later.
    if ! grep -q "CREATE ROLE ${DB_USER} WITH LOGIN" "$PROVISION_SQL"; then
        die "role name mismatch.

  template would create  ${PROVISION_RUNTIME}_app
  this script connects as  ${DB_USER}

  DB_USER must be the role name the canonical template creates, i.e. the prefix
  with the _app suffix: ${PROVISION_RUNTIME}_app. The template is shared with the
  VPS and is not edited here."
    fi

    # A placeholder left in the executable half means this script does not
    # know what the template needs. Send it to the database anyway and psql
    # will create a role literally named "<runtime>_app".
    if grep -qE '<[a-z_-]+>' "$PROVISION_SQL"; then
        grep -nE '<[a-z_-]+>' "$PROVISION_SQL" >&2
        die "the provisioning template has placeholders this script does not substitute. Listed above; refusing to guess."
    fi

    if [ "$ROLE_ALREADY_EXISTS" -eq 1 ]; then
        # Drop the CREATE ROLE statement -- the only non-idempotent line. It spans
        # several lines, so the strip runs to the semicolon that ends it rather
        # than to the end of the line that starts it: taking only the first line
        # leaves a dangling PASSWORD/NOSUPERUSER fragment and a syntax error that
        # says nothing about the real problem. Terminating on the semicolon also
        # keeps this correct if the template is ever reformatted onto one line.
        PROVISION_APPLY="${TMP_WORKDIR}/provision-apply.sql"
        awk '
            /^CREATE ROLE / {skip=1}
            skip && /;[[:space:]]*$/ {skip=0; next}
            skip            {next}
            {print}
        ' "$PROVISION_SQL" > "$PROVISION_APPLY"

        if grep -qE '^CREATE ROLE ' "$PROVISION_APPLY"; then
            die "could not remove CREATE ROLE from the substituted template. The role
  ${DB_USER} already exists, so the template cannot be applied as written.
  Refusing to run a provisioning script half-understood."
        fi

        # The strip removes one statement. If it ever removes more -- a reformat of
        # the template that moves where CREATE ROLE ends is enough -- what is left
        # can be empty, and psql reports success on an empty file. The run would
        # then claim the grants were re-applied when none were, which is the exact
        # failure this branch exists to prevent.
        if ! grep -qiE 'GRANT|ALTER DEFAULT PRIVILEGES' "$PROVISION_APPLY"; then
            die "the executable template contains no grants.
  role    ${DB_USER} already exists, so CREATE ROLE was stripped
  left    nothing that grants anything

The grants were NOT applied. Refusing to report success for an empty script."
        fi
    else
        PROVISION_APPLY="$PROVISION_SQL"
    fi

    if [ -s "$PROVISION_APPLY" ]; then
        docker exec -i "$CORE_PG_CONTAINER" psql -v ON_ERROR_STOP=1 -q \
            -U "$CORE_DB_ADMIN_USER" -d postgres < "$PROVISION_APPLY" \
            || die "role provisioning failed. ${template} was not fully applied."
        if [ "$ROLE_ALREADY_EXISTS" -eq 1 ]; then
            ok "role ${DB_USER} exists; its grants re-applied to ${DB_NAME}"
        else
            ok "role ${DB_USER} created"
        fi
    else
        warn "no executable statements found in ${template}"
    fi
}

provision_object_store() {
    # Run inside this project's own image, which already depends on the MinIO SDK
    # (requirements.txt) and already builds a client (app/core/storage.py). No new
    # dependency and no `mc` binary is introduced to do this.
    # `-i` is load-bearing. The provisioning program arrives on stdin, and without
    # it python reads an empty stream, exits 0, and this reports an object store
    # that was never created. That is the ON_ERROR_STOP class of failure: the step
    # says it worked and nothing downstream ever learns otherwise.
    docker run --rm -i --network "$LOCAL_NETWORK" \
        -e CORE_MINIO_CONTAINER="$CORE_MINIO_CONTAINER" \
        -e CORE_MINIO_ROOT_USER="$CORE_MINIO_ROOT_USER" \
        -e CORE_MINIO_ROOT_PASSWORD="$CORE_MINIO_ROOT_PASSWORD" \
        -e MINIO_DEFAULT_BUCKET="$MINIO_DEFAULT_BUCKET" \
        -e MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
        -e MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
        --entrypoint python "$API_IMAGE" - <<'EMBEDDED_PY' || die "object-store provisioning failed"
import os
import sys
from minio import Minio, MinioAdmin
from minio.credentials import StaticProvider
from minio.error import MinioAdminException, S3Error

endpoint = os.environ["CORE_MINIO_CONTAINER"] + ":9000"

client = Minio(
    endpoint,
    access_key=os.environ["CORE_MINIO_ROOT_USER"],
    secret_key=os.environ["CORE_MINIO_ROOT_PASSWORD"],
    secure=False,
)

# User management is NOT on the Minio class in minio-py 7.2.7 -- the admin API
# lives on a separate MinioAdmin, which takes a credentials Provider rather than
# an access/secret pair. Calling client.admin_user_add() raises AttributeError,
# which is what this first did.
admin = MinioAdmin(
    endpoint,
    credentials=StaticProvider(
        os.environ["CORE_MINIO_ROOT_USER"], os.environ["CORE_MINIO_ROOT_PASSWORD"]
    ),
    secure=False,
)

bucket = os.environ["MINIO_DEFAULT_BUCKET"]
user = os.environ["MINIO_ACCESS_KEY"]

if client.bucket_exists(bucket):
    print("  bucket " + bucket + " already exists")
else:
    client.make_bucket(bucket)
    print("  bucket " + bucket + " created")

# A user that already exists cannot have its secret changed through the S3 API, so
# an existing user is reported and never silently re-created: doing that would
# break every other client already holding the old secret.
# MinioAdmin does not raise S3Error for a missing user; it raises its own
# MinioAdminException carrying an HTTP 404 whose JSON body names
# XMinioAdminNoSuchUser. Both are handled, because catching only S3Error let the
# first missing user abort provisioning with an unhandled traceback.
try:
    admin.user_info(user)
    print("  object-store user " + user + " already exists")
except (S3Error, MinioAdminException) as exc:
    detail = str(exc)
    if not any(marker in detail for marker in ("NoSuchUser", "does not exist", "ResourceNotFound")):
        raise
    admin.user_add(user, os.environ["MINIO_SECRET_KEY"])
    print("  object-store user " + user + " created")

# readwrite is MinIO's canned policy. Locally that is the right scope: the bucket
# is this project's own, and a hand-built policy JSON would be untested here and
# silently wrong in production. Deployed, the policy is scoped to one bucket.
admin.policy_set("readwrite", user=user)

# The post-condition is what matters. A policy that failed to attach otherwise
# leaves a credential that authenticates successfully and cannot read anything.
# This connects as the NEW user -- not as root -- so it proves the credential and
# its policy together. Checking with the root client would pass even if the user
# had no access at all.
app_client = Minio(
    endpoint,
    access_key=user,
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)
try:
    if not app_client.bucket_exists(bucket):
        sys.exit("object-store user " + user + " cannot see bucket " + bucket)
    print("  object-store user " + user + " verified")
except S3Error as exc:
    sys.exit("object-store user " + user + " could not be verified: " + exc.code)
EMBEDDED_PY
    ok "object store ready (${MINIO_DEFAULT_BUCKET}, ${MINIO_ACCESS_KEY})"
}

# ── schema ───────────────────────────────────────────────────────────────────
# infra/schema.sql, never the models. The models are 94 operations stale
# (TICKET-019), so autogenerate would load a wrong schema silently.
apply_schema() {
    local schema="${PROJECT_ROOT}/infra/schema.sql"

    if psql_app_db -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='token_blacklist'" \
        | grep -q 1; then
        ok "schema already applied (token_blacklist present); skipping"
        return 0
    fi

    # ON_ERROR_STOP=1 is not hardening. Without it psql logs the error, keeps
    # going, exits 0, and the schema is reported loaded when it was never built —
    # how TICKET-007, -008 and -017 stayed hidden.
    docker exec -i "$CORE_PG_CONTAINER" psql -v ON_ERROR_STOP=1 -q \
        -U "$CORE_DB_ADMIN_USER" -d "$DB_NAME" < "$schema" \
        || die "schema load failed. ${schema} was NOT applied — the database is incomplete."

    psql_app_db -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='token_blacklist'" \
        | grep -q 1 \
        || die "token_blacklist is missing after the load; every authenticated request will fail (TICKET-017)."

    ok "schema applied from ${schema#"$PROJECT_ROOT"/}"
}

# ── migrations ───────────────────────────────────────────────────────────────
# `alembic/env.py` reads its DSN from app.core.settings, which validates the whole
# object at import — so the job cannot start with a partial environment. Every
# setting is therefore forwarded explicitly, and the DB credential is replaced
# with the elevated one. Secrets are forwarded by name (`-e KEY`) rather than by
# value, so they never appear in this process's arguments.
run_migrations() {
    # The rules around this -- which keys are forwarded, which are declared by the
    # compose file, why the DB credential is replaced -- live in the shared lib so
    # the gate cannot end up with a second, slightly different list.
    # shellcheck source=infra/local/scripts/lib-migrate.sh
    . "${SCRIPT_DIR}/scripts/lib-migrate.sh"
    migrate_env_args "$COMPOSE_FILE" "$CORE_DB_ADMIN_USER" "$CORE_DB_ADMIN_PASSWORD"

    if ! docker compose -f "$COMPOSE_FILE" run --rm "${MIGRATE_ENV_ARGS[@]}" migrate \
            alembic upgrade head; then
        die "migrations failed. The schema in ${DB_NAME} is at an unknown revision."
    fi

    # One head, and the database is on it. Two heads means the history branched,
    # and alembic will not choose for us (TICKET-009).
    local heads current
    heads="$(docker compose -f "$COMPOSE_FILE" run --rm "${MIGRATE_ENV_ARGS[@]}" migrate \
        alembic heads 2>/dev/null | grep -cE '\(head\)' || true)"
    if [ "${heads:-0}" -ne 1 ]; then
        die "${heads} migration heads found; expected exactly 1. Two heads means the revision history branched (TICKET-009)."
    fi

    current="$(alembic_current_revision "$COMPOSE_FILE")"
    [ -n "$current" ] || die "could not read the applied revision from ${DB_NAME}"

    ok "migrations applied; ${DB_NAME} is at ${current}"
}

# ── seed ─────────────────────────────────────────────────────────────────────
run_seed() {
    local seed_dir="${PROJECT_ROOT}/infra/local/seed"
    local data_dir="${PROJECT_ROOT}/infra/local/data"

    [ -d "$seed_dir" ] || die "the committed seed folder is missing: ${seed_dir}"

    mkdir -p "$data_dir"

    # `etl/get_hash.py` hardcodes `mktemp -d /tmp/opencode.XXXXXX` and exits
    # non-zero when that parent does not exist. Created here rather than patched
    # there, because that file is shared with the other ETL callers.
    mkdir -p /tmp/opencode

    # The committed rows are copied rather than loaded in place: `.gitignore`
    # excludes `**/data/*` so a CSV committed there would be invisible to git and
    # silently absent from a fresh clone — a setup that loads nothing and reports
    # success. See infra/local/seed/README.md.
    cp "$seed_dir"/*.csv "$data_dir"/

    # The seed account is created here rather than committed, for the reason
    # infra/local/seed/README.md gives: a committed file would carry either a
    # password or a fixed hash, and a fixed hash means one shared password plus a
    # salt that can never be regenerated. get_hash.py re-salts on every run.
    local plain="${data_dir}/fsm_users_plain.csv"
    local hashed="${data_dir}/fsm_users.csv"
    rm -f "$plain"

    {
        printf 'user_id,email,user_name,plain_password,user_role,photo_path,created_at\n'
        printf '%s,%s,%s,%s,%s,,%s\n' \
            "$SEED_USER_ID" "$SEED_USER_EMAIL" "$SEED_USER_NAME" \
            "$SEED_USER_PASSWORD" "$SEED_USER_ROLE" "$(date -u +'%Y-%m-%d %H:%M:%S+00')"
    } > "$plain"
    # The plaintext file is removed immediately: it exists only long enough for
    # get_hash.py, and it lives in the git-ignored folder so a crash mid-run
    # cannot leave it in something a developer might later commit.
    "${PROJECT_ROOT}/venv/bin/python" "${PROJECT_ROOT}/etl/get_hash.py" "$plain" "$hashed" \
        || die "hashing the seed account's password failed"
    rm -f "$plain"

    # `--allow-business-data` is required and is a considered choice here, not an
    # oversight. `fsm_users`, `markets`, `equipments` and `technicians` are on the
    # loader's BUSINESS_TABLES list, so without this flag they are skipped and the
    # local environment loads nothing the gate can use. It is safe here for one
    # reason and one reason only: every row loaded is a synthetic row committed in
    # infra/local/seed/ or generated above. The flag is what makes that guarantee
    # load-bearing rather than a matter of trust — it is also what would load
    # business rows from any other CSV a developer drops into the folder, which is
    # why the folder stays git-ignored and this script never reads a CSV it did
    # not just copy.
    # Seeding runs as the ADMINISTRATIVE role, not the application role, for the
    # same reason the schema does: seeding is an administrative action.
    #
    # Concretely, the canonical least-privilege template (a no-touch file shared
    # with the VPS) deliberately withholds privileges on reference tables the
    # application never reads -- `uom`, `materials`, `preliquidated`, `services`
    # -- and `information_schema.tables` only lists tables the connected role can
    # see. Loading as the app role therefore reported "Table 'uom' does not exist"
    # for tables that do exist, and silently loaded nothing: the gate would then
    # have failed on missing reference data and the warning would have pointed at
    # the wrong thing entirely. Widening the app role's grants to make the loader
    # work would undo the least-privilege contract, so the loader gets the
    # administrator instead.
    "${PROJECT_ROOT}/etl/seed_db.sh" \
        --db-host "$CORE_PG_CONTAINER" \
        --db-user "$CORE_DB_ADMIN_USER" \
        --db-name "$DB_NAME" \
        --data-folder "$data_dir" \
        --allow-business-data \
        || die "seeding failed. ${DB_NAME} has the schema but no reference data."

    ok "seed data loaded from ${seed_dir#"$PROJECT_ROOT"/}"
}

# ── summary ──────────────────────────────────────────────────────────────────
# The developer must be able to see what was actually bound and against what,
# because a wrong host is otherwise discovered from a failed request.
print_summary() {
    local api_binding pg_binding minio_binding

    api_binding="$(docker compose -f "$COMPOSE_FILE" port api 8000 2>/dev/null || printf 'not published')"
    pg_binding="$(docker port "$CORE_PG_CONTAINER" 5432/tcp 2>/dev/null | head -1 || printf 'unknown')"
    minio_binding="$(docker port "$CORE_MINIO_CONTAINER" 9000/tcp 2>/dev/null | head -1 || printf 'unknown')"

    printf '\n%s%sLocal environment ready%s\n' "$BOLD" "$GREEN" "$RESET"
    # Measured, not assumed. The previous pattern looked for `"name":"..."`, but
    # `compose config --format json` pretty-prints (`"name": "..."`), so the grep
    # never matched and the `||` fallback printed a hardcoded name that happened to
    # be right. A summary that reports a value it did not read is worse than no
    # summary: it is the one line an operator trusts when something else is wrong.
    local compose_project
    compose_project="$(docker compose -f "$COMPOSE_FILE" config --format json 2>/dev/null \
        | grep -m1 -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' | cut -d'"' -f4 || true)"
    [ -n "$compose_project" ] || die "could not read the compose project name from ${COMPOSE_FILE}"
    [ "$compose_project" = "app-tickets-local" ] || die "$(cat <<EOF
compose project name mismatch.

  compose resolves to  ${compose_project}
  this stack owns      app-tickets-local

  Another project's COMPOSE_PROJECT_NAME is in force, so this stack's containers
  would be created inside that project's namespace, where its owner could remove
  them as orphans. Refusing to continue.
EOF
)"
    printf '  %-22s %s\n' "compose project" "$compose_project"
    printf '  %-22s %s\n' "network" "$LOCAL_NETWORK (owned by this project)"
    printf '  %-22s %s\n' "core compose" "$CORE_COMPOSE_COMMAND"
    printf '  %-22s %s\n' "core owner" "another project — started outside this repository"
    printf '\n'
    printf '  %-22s %s\n' "API" "${api_binding}"
    printf '  %-22s %s\n' "${CORE_PG_CONTAINER}" "${pg_binding}"
    printf '  %-22s %s\n' "${CORE_MINIO_CONTAINER}" "${minio_binding}"
    printf '\n'
    dim "Native (no containers) access to the same dependencies: use DB_HOST=127.0.0.1 DB_PORT=5435"
    dim "and MINIO_ENDPOINT=127.0.0.1 MINIO_PORT=9000 in .env. See .env.example."
    printf '\n'
}

# ── main ─────────────────────────────────────────────────────────────────────
main() {
    TMP_WORKDIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_WORKDIR"' EXIT

    step "Configuration"
    load_env

    # This project's containers must never land in another project's compose
    # namespace. `.env` carried `COMPOSE_PROJECT_NAME=infrastructure-companies-v2`,
    # which is the CORE's project name, and `COMPOSE_PROJECT_NAME` outranks the
    # `name:` in our own compose file -- so this stack's api container was created
    # as `infrastructure-companies-v2-api-1`. That is not untidy: the core's owner
    # running `docker compose down --remove-orphans` in their own directory would
    # treat our container as an orphan of their project and remove it. Set here,
    # after load_env, and reserved above so `.env` cannot reintroduce it.
    COMPOSE_PROJECT_NAME="app-tickets-local"
    export COMPOSE_PROJECT_NAME

    require_env \
        DB_NAME DB_USER DB_PASSWORD \
        MINIO_DEFAULT_BUCKET MINIO_ACCESS_KEY MINIO_SECRET_KEY \
        SEED_USER_ID SEED_USER_EMAIL SEED_USER_NAME SEED_USER_PASSWORD SEED_USER_ROLE \
        CORE_COMPOSE_COMMAND \
        CORE_DB_ADMIN_USER CORE_DB_ADMIN_PASSWORD \
        CORE_MINIO_ROOT_USER CORE_MINIO_ROOT_PASSWORD
    # The core's compose file is resolved from the configured key. It is read, and
    # only to confirm the file is there: this project neither starts nor stops it,
    # so `docker compose config` (which executes nothing) is the safe check.
    if [ ! -f "$CORE_COMPOSE_COMMAND" ]; then
        die "CORE_COMPOSE_COMMAND points at a file that does not exist: ${CORE_COMPOSE_COMMAND}
  key owner  the project that operates the core
  expected   that project's compose file, or a path to it in .env"
    fi
    ok "configuration read from .env"
    info "core compose: ${CORE_COMPOSE_COMMAND}"

    # Read from this project's own compose rather than repeated here, so the two
    # cannot drift apart and leave the connect scoped to a network that no service
    # is actually on.
    # Read from this project's own compose rather than repeated here, then checked
    # against the literal the connect command uses. The compose file stays the
    # single source of truth; the literal in the command stays visible; and a rename
    # that updates one without the other fails here instead of at connect time.
    EXPECTED_NETWORK="app-tickets-local-net"
    LOCAL_NETWORK="$(awk '/^networks:/{f=1;next} f && /^    name:/{print $2; exit}' "$COMPOSE_FILE")"
    [ -n "$LOCAL_NETWORK" ] || die "could not read the network name from ${COMPOSE_FILE}"
    [ "$LOCAL_NETWORK" = "$EXPECTED_NETWORK" ] || die "$(cat <<EOF
network name mismatch.

  compose declares   ${LOCAL_NETWORK}
  the connect uses   ${EXPECTED_NETWORK}

Rename both together, or the connect would attach the core's containers to a
network this stack is not on. Refusing to guess which one is current.
EOF
)"
    ok "local network: ${LOCAL_NETWORK}"

    # Same rule as the network name, for the same reason: the image tags are read
    # out of the compose file rather than repeated here, so a tag that exists in
    # one place and not the other fails loudly instead of at probe time.
    API_IMAGE="$(awk '/^  api:/{s=1} s && /^    image:/{print $2; exit}' "$COMPOSE_FILE")"
    MIGRATE_IMAGE="$(awk '/^  migrate:/{s=1} s && /^    image:/{print $2; exit}' "$COMPOSE_FILE")"
    [ -n "$API_IMAGE" ] || die "could not read the api image tag from ${COMPOSE_FILE}"
    [ -n "$MIGRATE_IMAGE" ] || die "could not read the migrate image tag from ${COMPOSE_FILE}"
    ok "images: ${API_IMAGE}, ${MIGRATE_IMAGE}"

    step "Shared core"
    assert_core_running

    step "Images"
    if [ "$SKIP_BUILD" -eq 1 ]; then
        warn "skipping build (--skip-build)"
    else
        docker compose -f "$COMPOSE_FILE" build api migrate
        ok "images built"
    fi

    step "Network"
    # `docker compose create` creates the network and the containers without
    # starting anything, which is what we need here: the network must exist before
    # the connect, and no service may start before the core is confirmed usable.
    docker compose -f "$COMPOSE_FILE" create
    if network_exists "$LOCAL_NETWORK"; then
        ok "network ${LOCAL_NETWORK} ready"
    else
        die "compose did not create the network ${LOCAL_NETWORK}"
    fi
    connect_core_to_local_network

    step "Readiness"
    wait_for_postgres
    ok "${CORE_PG_CONTAINER} accepts connections"
    wait_for_minio
    ok "${CORE_MINIO_CONTAINER} answers its health endpoint from ${LOCAL_NETWORK}"

    step "Database"
    ensure_database

    step "Schema"
    apply_schema

    step "Migrations"
    run_migrations

    # After the schema and the migrations, because the template grants on the
    # tables by name and migration 0001 adds one.
    step "Provisioning"
    provision_database
    provision_object_store

    step "Seed"
    run_seed

    step "API"
    docker compose -f "$COMPOSE_FILE" up -d api
    ok "api started"

    print_summary
}

main "$@"
