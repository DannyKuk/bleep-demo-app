import asyncio
import hmac
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from demo_app import faults
from demo_app.config import Settings, load_settings

log = logging.getLogger("demo_app")

PAGE = (Path(__file__).parent / "page.html").read_text()
ERROR_LOG_INTERVAL_S = 5.0


class FaultRequest(BaseModel):
    password: str = ""


class State:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.started = time.monotonic()
        self.error_reason: str | None = None
        self.leak: faults.Leak | None = None
        self.leak_task: asyncio.Task[None] | None = None

    def unhealthy_reason(self) -> str | None:
        if self.error_reason:
            return self.error_reason
        limit = self.settings.fail_after_s
        if limit is not None and time.monotonic() - self.started >= limit:
            return f"FAIL_AFTER_S={limit:g} elapsed, marking the service unhealthy"
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    state = State(settings)

    async def report_unhealthy() -> None:
        while True:
            await asyncio.sleep(ERROR_LOG_INTERVAL_S)
            reason = state.unhealthy_reason()
            if reason:
                log.error("service unhealthy: %s", reason)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(report_unhealthy())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="bleep-demo-app", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.demo = state

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/health")
    def health() -> JSONResponse:
        reason = state.unhealthy_reason()
        if reason:
            log.error("health check failing: %s", reason)
            return JSONResponse({"status": "error"}, status_code=500)
        return JSONResponse({"status": "ok"})

    @app.get("/api/status")
    def status() -> dict:
        return {
            "uptime_s": int(time.monotonic() - state.started),
            "faults_enabled": settings.demo_password is not None,
            "healthy": state.unhealthy_reason() is None,
            "config": {
                "host": settings.host,
                "host_is_loopback": settings.host_is_loopback,
                "fail_after_s": settings.fail_after_s,
            },
        }

    def check_password(body: FaultRequest) -> None:
        if settings.demo_password is None:
            raise HTTPException(403, "fault buttons are disabled: DEMO_PASSWORD is not set")
        if not hmac.compare_digest(body.password.encode(), settings.demo_password.encode()):
            log.warning("fault request rejected: wrong password")
            raise HTTPException(401, "wrong password")

    @app.post("/api/faults/hang")
    async def fault_hang(body: FaultRequest) -> dict:
        check_password(body)
        log.debug("fault triggered: hang")
        asyncio.get_running_loop().call_later(0.2, faults.hang)
        return {"triggered": "hang"}

    @app.post("/api/faults/error")
    def fault_error(body: FaultRequest) -> dict:
        check_password(body)
        state.error_reason = "cache connection pool exhausted (0/20 connections available)"
        return {"triggered": "error"}

    @app.post("/api/faults/leak")
    async def fault_leak(body: FaultRequest) -> dict:
        check_password(body)
        if state.leak is None:
            log.debug("fault triggered: leak")
            state.leak = faults.Leak()
            state.leak_task = asyncio.create_task(state.leak.run())
        return {"triggered": "leak"}

    @app.post("/api/faults/crash")
    def fault_crash(body: FaultRequest) -> dict:
        check_password(body)
        log.debug("fault triggered: crash")
        faults.crash()
        return {"triggered": "crash"}

    return app
