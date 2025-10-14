"""Background worker for cleaning up expired chat media."""

from __future__ import annotations

import asyncio
from typing import Optional

from config import get_settings
from services.media_service import MediaDownloadDisabled, cleanup_expired_media_batch
from utils.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)

_worker_task: Optional[asyncio.Task] = None


async def start_media_cleanup_worker() -> None:
    """Start the media cleanup background loop."""

    global _worker_task
    if _worker_task and not _worker_task.done():
        return

    interval_minutes = max(settings.media_cleanup_interval_minutes, 1)
    loop = asyncio.get_running_loop()
    _worker_task = loop.create_task(_cleanup_loop(interval_minutes))


async def stop_media_cleanup_worker() -> None:
    """Stop the media cleanup background loop."""

    global _worker_task
    task = _worker_task
    if not task:
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        _worker_task = None


async def _cleanup_loop(interval_minutes: int) -> None:
    delay_seconds = interval_minutes * 60

    while True:
        try:
            result = await cleanup_expired_media_batch()
            if result["deleted"] or result["failed"]:
                logger.info(
                    "Media cleanup iteration",
                    extra={"deleted": result["deleted"], "failed": result["failed"]},
                )
        except asyncio.CancelledError:
            raise
        except MediaDownloadDisabled:
            logger.info("Media download disabled; stopping cleanup worker")
            break
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Media cleanup iteration failed", exc_info=exc)

        await asyncio.sleep(delay_seconds)


async def run_single_cleanup() -> dict:
    """Trigger a single cleanup batch (manual invocation)."""

    try:
        return await cleanup_expired_media_batch()
    except MediaDownloadDisabled:
        logger.info("Media download disabled; cleanup skipped")
        return {"deleted": 0, "failed": 0}
