# ============================================================
# Stage 1 of 2: migrate
# ============================================================
# Built from this same source as the runtime image, on purpose. A migration must
# see the same app/models the application will run, otherwise "what migrated" and
# "what runs" are different code and the divergence surfaces later as a runtime
# error. This stage exists because `alembic` is in requirements.txt (so the package
# was installed) while only `app/` was copied: the image could start and pass its
# healthcheck, yet `alembic upgrade head` failed on a missing config.
#
# This is a JOB, not a service. Never add a restart policy to it: a failed
# migration must stop, not retry against a Postgres shared with other tenants.
#
# WHAT CREDENTIAL RUNS IT. It runs with the administrator credentials the operator
# supplies, because schema change belongs to whoever owns the schema. There is no
# dedicated migration role, and that is deliberate rather than an omission: on a
# server where ownership is never granted to an application credential,
# `GRANT CREATE ON SCHEMA` permits creating new objects but not altering existing
# ones, so such a role could create an empty table and could not alter a real one.
# Making it able to would require giving it ownership, which removes the boundary
# this job is supposed to sit outside of. See infra/provision/README.md.
#
# The practical consequence: DB_USER/DB_PASSWORD passed to this job must be
# elevated, and must therefore never be the values the running service uses. The
# runtime role holds DML only and will fail here with a permission error, which is
# the correct outcome rather than a misconfiguration to work around.
FROM python:3.12.12-slim-bookworm AS migrate

WORKDIR /srv

# libpq5 only: the migration path does not render PDFs, so the WeasyPrint stack is
# not needed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# env.py imports app.core.settings and app.models, so all three are required.
COPY app/ /srv/app/
COPY alembic/ /srv/alembic/
COPY alembic.ini /srv/alembic.ini

# No connection string is baked in: alembic/env.py reads the DSN from the
# application settings, so the same image is safe to build once and run against
# any environment.
CMD ["alembic", "upgrade", "head"]

# ============================================================
# Stage 2 of 2: runtime (default — the image a plain `docker build` must produce)
# ============================================================
FROM python:3.12.12-slim-bookworm AS runtime

# Pinned base image: an unpinned tag turns a routine image rebuild
# into an unverified change of Python patch level and Debian release.

# The application uses absolute imports (`from app.core.settings
# import settings`), so the image must keep the `app` package
# directory. Copying the CONTENTS of app/ into WORKDIR would make
# `app.main:app` unresolvable and the container would never start.
WORKDIR /srv

# Fixed identity for the runtime user. Stated here as ENV so there is one source
# of truth for it, consumed by the useradd below and read by infra/local/ to
# chown CHUNK_DIR. A literal repeated in both places would drift silently, and
# the drift surfaces as a permissions error on the first chunked upload.
#
# Outside the 100-999 system range on purpose: uids there belong to accounts that
# other packages may already define.
ENV APP_UID=10001 \
    APP_GID=10001

# Runtime system libraries. Everything here is needed to RUN the service:
#   libpq5           psycopg2 runtime
#   libpango*,
#   libharfbuzz0b,
#   libopenjp2-7,
#   libjpeg62-turbo  WeasyPrint (app/services/worksheet_service.py imports it at
#                    module load, so a missing library aborts the whole API, not
#                    only PDF generation)
#   fonts-dejavu-core glyphs for the generated PDF reports
#   curl             container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libopenjp2-7 \
    libjpeg62-turbo \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build toolchain, installed for pip and removed below. psycopg2-binary ships
# wheels, so on a normal build nothing invokes a compiler - which is exactly why
# it must not simply stay: an installed compiler nobody uses is still a compiler,
# and the removal is what makes the final layer's package list trustworthy.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Drop the toolchain AFTER the install that may need it. `--autoremove` takes the
# packages gcc and libpq-dev pulled in as dependencies; `libpq5` survives because
# the layer above installed it directly, so it is marked manual and not orphaned.
RUN apt-get purge -y --auto-remove gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && (command -v gcc >/dev/null && echo "gcc still present" && exit 1 || true)

# A user with no login shell and no home directory: the service writes only to
# CHUNK_DIR, and nothing in the container needs to be interactive.
RUN groupadd --gid "$APP_GID" app \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --no-create-home \
        --shell /usr/sbin/nologin app

COPY app/ /srv/app/

# Owned by the runtime user so a bind mount over it does not shadow the
# ownership. See infra/local/docker-compose.yml, which also sets this explicitly.
RUN mkdir -p /tmp/upload_chunks && chown "$APP_UID:$APP_GID" /tmp/upload_chunks

USER app

EXPOSE 8000

# Deployment gates poll this endpoint: it fails if the app cannot
# import (settings, database driver, WeasyPrint) or cannot serve.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/openapi.json || exit 1

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "app.main:app"]
