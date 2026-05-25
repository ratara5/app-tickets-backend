# import sys
# import os
# sys.path.insert(0, os.path.dirname(__file__))

from app.server import create_app
from app.core.settings import settings

from app.core.logger import setup_logging

setup_logging()

app = create_app()

# if __name__ == "__main__":
    # app.run(
        # host="0.0.0.0",
        # port=settings.port,
        # debug=settings.flask_debug,
        # use_reloader=settings.flask_use_reloader
    # )