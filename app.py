"""FastAPI application entrypoint for the Parcelo WhatsApp service."""

from fastapi import FastAPI

from config import get_settings
from utils.logging import configure_logging

from luminous_webhook import router as luminous_router


settings = get_settings()
logger = configure_logging(settings.log_level)


app = FastAPI(title="Parcelo WhatsApp Service", version="0.1.0")

app.include_router(luminous_router)


@app.get("/healthz", tags=["System"])
async def health_check() -> dict[str, str]:
    """Return basic service health information."""

    logger.debug("Health check invoked")
    return {"status": "ok", "environment": settings.environment}
