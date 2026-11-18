"""The runtime faults. Each one logs what a real failure of that kind would log."""

import asyncio
import logging
import os
import signal
import threading

log = logging.getLogger("demo_app.faults")

MB = 1024 * 1024
# The leak grows fast up to its budget, then slowly, so with a 256 MB limit `/health` fails for
# about five minutes before the out-of-memory kill: long enough for a watcher to notice.
LEAK_BUDGET_BYTES = 128 * MB
LEAK_FAST_CHUNK_BYTES = 8 * MB
LEAK_SLOW_CHUNK_BYTES = MB // 4
LEAK_INTERVAL_S = 1.0
LEAK_LOG_EVERY_BYTES = 40 * MB


def hang() -> None:
    """Block the event loop for good, so nothing answers until the process restarts.

    Uvicorn's SIGTERM handler only asks the blocked loop to stop, so a restart would wait out
    the stop timeout. A handler that exits at once lets `docker stop` work during the hang.
    """
    log.warning("session sync: waiting for lock held by worker 3")
    signal.signal(signal.SIGTERM, _exit_on_signal)
    signal.signal(signal.SIGINT, _exit_on_signal)
    threading.Event().wait()


def _exit_on_signal(signum: int, _frame: object) -> None:
    os._exit(128 + signum)


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
    """Holds on to more memory every second and logs the cache growing. Past its budget it makes
    the service unhealthy and grows slower, until the container runs out of memory."""

    def __init__(
        self,
        budget_bytes: int = LEAK_BUDGET_BYTES,
        fast_chunk_bytes: int = LEAK_FAST_CHUNK_BYTES,
        slow_chunk_bytes: int = LEAK_SLOW_CHUNK_BYTES,
    ) -> None:
        self.budget_bytes = budget_bytes
        self.fast_chunk_bytes = fast_chunk_bytes
        self.slow_chunk_bytes = slow_chunk_bytes
        self.chunks: list[bytes] = []
        self.size_bytes = 0

    @property
    def over_budget(self) -> bool:
        return self.size_bytes > self.budget_bytes

    def unhealthy_reason(self) -> str | None:
        if not self.over_budget:
            return None
        return (
            f"report cache holds {self.size_bytes // MB} MB, over its {self.budget_bytes // MB} MB"
            " budget; report requests time out"
        )

    def grow(self) -> None:
        """Add one entry: a big one while under the budget, a small one past it."""
        was_over = self.over_budget
        before = self.size_bytes
        chunk = self.slow_chunk_bytes if was_over else self.fast_chunk_bytes
        self.chunks.append(b"\xa5" * chunk)
        self.size_bytes += chunk
        if not was_over and self.over_budget:
            log.error("%s", self.unhealthy_reason())
        if self.size_bytes // LEAK_LOG_EVERY_BYTES > before // LEAK_LOG_EVERY_BYTES:
            log.warning(
                "report cache holds %d entries (%d MB), no eviction",
                len(self.chunks),
                self.size_bytes // MB,
            )

    async def run(self) -> None:
        log.warning("report cache: unbounded growth, eviction disabled")
        while True:
            self.grow()
            await asyncio.sleep(LEAK_INTERVAL_S)
