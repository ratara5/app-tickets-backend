#!/usr/bin/env bash
# Shared by setup.sh and gate-local.sh. Sourced, never executed.
#
# Why this exists: `alembic/env.py` reads its DSN from `app.core.settings`, which
# validates the whole object at import, so the migrate job cannot start with a
# partial environment. Every required setting is therefore forwarded explicitly.
# That list is long and the rules around it are subtle, and the gate needs it for
# exactly the same reason the bring-up does -- so it lives here once instead of
# being written twice and drifting.

# Keys the compose file already declares for a service. Read out of the file
# rather than hardcoded, so a key added there cannot be silently missed here.
#
# Forwarding every key blindly is what broke this once: the compose file declares
# the values that must differ INSIDE a container (DB_HOST, DB_PORT,
# MINIO_ENDPOINT and friends), `docker compose run -e KEY` takes its value from
# this shell, and this shell holds the host-run values from .env. The migrate job
# dialled localhost:5435 from inside the network and was refused.
compose_owned_keys() {
    local compose_file="$1"
    local service="$2"

    awk -v header="^  ${service}:" '
        $0 ~ header              {s=1; next}
        s && /^    environment:/ {e=1; next}
        e && /^    [a-zA-Z]/     {exit}
        e && /^      [A-Z_][A-Z0-9_]*:/ {print substr($0, 7, index($0, ":") - 7)}
    ' "$compose_file"
}

# Fills the global array MIGRATE_ENV_ARGS with the `-e` flags for
# `docker compose run`. Secrets are forwarded by NAME (`-e KEY`) rather than by
# value wherever the value is already an environment variable, so they never
# appear in this process's arguments. The DB credential is the one exception: it
# must be REPLACED with the elevated one, because the runtime role holds DML only
# and cannot read alembic_version.
#
# Requires the caller's environment to hold the .env values; the gate must export
# what it read for `-e KEY` to find it.
migrate_env_args() {
    local compose_file="$1"
    local admin_user="$2"
    local admin_password="$3"

    MIGRATE_ENV_ARGS=()

    local compose_owned key ck skip
    compose_owned="$(compose_owned_keys "$compose_file" migrate)"

    while IFS= read -r key; do
        [ -n "$key" ] || continue
        skip=0
        for ck in $compose_owned; do
            if [ "$ck" = "$key" ]; then skip=1; break; fi
        done
        [ "$skip" -eq 1 ] && continue
        MIGRATE_ENV_ARGS+=(-e "$key")
    done < <(env | cut -d= -f1 | grep -E '^[A-Z_][A-Z0-9_]*$')

    MIGRATE_ENV_ARGS+=(-e "DB_USER=${admin_user}")
    MIGRATE_ENV_ARGS+=(-e "DB_PASSWORD=${admin_password}")
}

# The applied revision, read the way alembic itself marks it.
#
# Never match on the shape of a revision id. This history uses NAMED revisions
# (`0003_join_table_keys`), so a `[0-9a-f]{7,}` pattern matches nothing and a
# healthy database is reported as `unknown revision`. Alembic marks heads with a
# literal "(head)", which is revision-format independent.
alembic_current_revision() {
    local compose_file="$1"

    docker compose -f "$compose_file" run --rm "${MIGRATE_ENV_ARGS[@]}" migrate \
        alembic current 2>/dev/null \
        | grep -E '\(head\)' | awk '{print $1}' | head -1
}
