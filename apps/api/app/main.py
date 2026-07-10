import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .api import router
from .config import get_settings
from .db import engine
from .observability import (
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
)
from .services.checkout import expire_stale_orders

settings = get_settings()
configure_logging(settings.json_logs)
logger = logging.getLogger(__name__)


def _run_sweep() -> int:
    with Session(engine) as session:
        return expire_stale_orders(session)


async def _reservation_sweep_loop() -> None:
    interval = settings.reservation_sweep_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_run_sweep)
        except Exception:
            logger.exception("Reservation sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    sweep_task: asyncio.Task | None = None
    if settings.reservation_sweep_interval_seconds > 0:
        sweep_task = asyncio.create_task(_reservation_sweep_loop())
    try:
        yield
    finally:
        if sweep_task is not None:
            sweep_task.cancel()
            try:
                await sweep_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="QY & YX's Cafe API",
    version="1.0.0",
    description="Matcha drinks cafe in Umeå, Sweden — order online, pick up at the counter.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added after CORS so they wrap it (outermost), guaranteeing the request-id
# header, access log, and security headers cover every response -- including
# CORS preflight replies and errors raised before reaching the router.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=settings.cookie_secure)
app.include_router(router)

os.makedirs(settings.uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")


@app.get("/healthz", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}
