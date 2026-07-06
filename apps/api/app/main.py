import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .api import router
from .config import get_settings
from .db import engine
from .services.checkout import expire_stale_orders

settings = get_settings()
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
    title="Matcha Demonstration Store API",
    version="1.0.0",
    description="SGD-only portfolio store. Test payments; duties, taxes and conversion excluded.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/healthz", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}
