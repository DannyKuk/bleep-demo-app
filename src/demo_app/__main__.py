import logging

import uvicorn

from demo_app.app import create_app
from demo_app.config import load_settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    log = logging.getLogger("demo_app")
    settings = load_settings()
    log.info("listening on %s:%d", settings.host, settings.port)
    if settings.fail_after_s is not None:
        log.info(
            "FAIL_AFTER_S=%g: the app will turn unhealthy after that many seconds",
            settings.fail_after_s,
        )
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
