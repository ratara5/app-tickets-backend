from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
#from fastapi_jwt_extended import JWTManager

from app.core import storage
from app.api.routes import all_router

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Fail at startup rather than on every photo.

    The bucket check runs once here instead of on every upload, so an unreachable
    object store stops the process with one actionable message instead of producing
    a retry storm per photo.
    """
    log.info(
        "minio_origins_resolved",
        internal=storage.settings.minio_internal.origin,
        public=storage.settings.minio_public.origin,
        region=storage.settings.minio_region,
    )
    storage.ensure_storage_ready()
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    #JWTManager(app)

    for router in all_router:
        app.include_router(router)
    return app
