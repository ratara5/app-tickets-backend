from .tickets import router as tickets_router
from .maintenances import router as maintenances_router
from .uploads import router as uploads_router
from .auth import router as auth_router
from .users import router as users_router
from .master import router as master_router

all_router = [tickets_router,
              maintenances_router,
              uploads_router,
              auth_router,
              users_router,
              master_router]
