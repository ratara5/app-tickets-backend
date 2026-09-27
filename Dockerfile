# Pinned base image: an unpinned tag turns a routine image rebuild
# into an unverified change of Python patch level and Debian release.
FROM python:3.12.12-slim-bookworm

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
