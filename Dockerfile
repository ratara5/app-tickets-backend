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

# Runtime system libraries:
#   libpq5          psycopg2 runtime (libpq-dev only ships headers)
#   libpango*,
#   libharfbuzz0b,
#   libopenjp2-7,
#   libjpeg62-turbo WeasyPrint (app/services/worksheet_service.py
#                   imports it at module load, so a missing library
#                   aborts the whole API, not only PDF generation)
#   fonts-dejavu-core  glyphs for the generated PDF reports
#   curl            container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libpq5 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libopenjp2-7 \
    libjpeg62-turbo \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /srv/app/

EXPOSE 8000

# Deployment gates poll this endpoint: it fails if the app cannot
# import (settings, database driver, WeasyPrint) or cannot serve.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/openapi.json || exit 1

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "app.main:app"]
