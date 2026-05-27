from .tickets import router as tickets_router
from .maintenances import router as maintenances_router
from .uploads import router as uploads_router

all_router = [tickets_router,
              maintenances_router,
              uploads_router]
