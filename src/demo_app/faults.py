"""The runtime faults. Each one logs what a real failure of that kind would log."""

import asyncio
import logging
import os
import threading

log = logging.getLogger("demo_app.faults")

LEAK_CHUNK_BYTES = 8 * 1024 * 1024
LEAK_INTERVAL_S = 1.0
LEAK_LOG_EVERY = 5


def hang() -> None:
    """Block the event loop for good, so nothing answers until the process restarts."""
    log.warning("session sync: waiting for lock held by worker 3")
    threading.Event().wait()


def crash() -> None:
    """Exit non-zero with a stack trace in the log, from a timer so the response goes out."""

    def run() -> None:
        try:
            refresh_session_cache({"user": "demo", "token": None})
        except Exception:
            log.critical("unhandled error in session refresh, shutting down", exc_info=True)
            logging.shutdown()
            os._exit(1)

    threading.Timer(0.3, run).start()


def refresh_session_cache(session: dict[str, str | None]) -> None:
    _decode_token(session)


def _decode_token(session: dict[str, str | None]) -> None:
    if session["token"] is None:
        raise RuntimeError("session token missing while refreshing cache entry for user 'demo'")


class Leak:
    """Holds on to a bit more memory every second and logs the cache growing."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    async def run(self) -> None:
        log.warning("report cache: unbounded growth, eviction disabled")
        while True:
            self.chunks.append(b"\xa5" * LEAK_CHUNK_BYTES)
            if len(self.chunks) % LEAK_LOG_EVERY == 0:
                size_mb = len(self.chunks) * LEAK_CHUNK_BYTES // (1024 * 1024)
                log.warning(
                    "report cache holds %d entries (%d MB), no eviction", len(self.chunks), size_mb
                )
            await asyncio.sleep(LEAK_INTERVAL_S)
