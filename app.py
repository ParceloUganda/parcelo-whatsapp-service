"""FastAPI application entrypoint for the Parcelo WhatsApp service."""

from fastapi import FastAPI

from config import get_settings
from utils.logging import configure_logging

from luminous_webhook import router as luminous_router
from workers.summary_worker import start_summary_worker, stop_summary_worker
from workers.media_cleanup_worker import start_media_cleanup_worker, stop_media_cleanup_worker


settings = get_settings()
logger = configure_logging(settings.log_level)


app = FastAPI(title="Parcelo WhatsApp Service", version="0.1.0")

app.include_router(luminous_router)


@app.get("/healthz", tags=["System"])
async def health_check() -> dict[str, str]:
    """Return basic service health information."""

    logger.debug("Health check invoked")
    return {"status": "ok", "environment": settings.environment}


@app.on_event("startup")
async def startup_event() -> None:
    await start_summary_worker()
    await start_media_cleanup_worker()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await stop_summary_worker()
    await stop_media_cleanup_worker()
