from fastapi import FastAPI
#from fastapi_jwt_extended import JWTManager

from app.core.settings import settings
from app.api.routes import all_router

def create_app() -> FastAPI:
    app = FastAPI()
    #JWTManager(app)

    for router in all_router:
        app.include_router(router)
    return app