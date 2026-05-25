from .tickets import router as tickets_router
from .mantenimientos import router as mantenimientos_router
from .uploads import router as uploads_router

all_router = [tickets_router,
              mantenimientos_router,
              uploads_router]
