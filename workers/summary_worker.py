"""Background worker to refresh session summaries and prune message history."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import get_settings
from services.summarization_service import maybe_generate_summary
from services.supabase_client import get_supabase_client
from utils.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_worker_task: Optional[asyncio.Task] = None


async def start_summary_worker() -> None:
    """Start the background task if not already running."""

    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    loop = asyncio.get_running_loop()
    _worker_task = loop.create_task(_summary_loop())


async def stop_summary_worker() -> None:
    """Stop the background task gracefully."""

    global _worker_task
    task = _worker_task
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _worker_task = None


async def _summary_loop() -> None:
    client = get_supabase_client()
    interval_minutes = max(settings.summary_refresh_minutes, 1)
    delay = interval_minutes * 60

    while True:
        try:
            sessions = await _fetch_stale_sessions(client, interval_minutes)
            for session in sessions:
                session_id = session.get("id")
                if not session_id:
                    continue
                await maybe_generate_summary(session_id)
                await _prune_old_messages(client, session_id, settings.llm_window_size)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Summary worker iteration failed", exc_info=exc)
        await asyncio.sleep(delay)


async def _fetch_stale_sessions(client, interval_minutes: int) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=interval_minutes)
    cutoff_iso = cutoff.isoformat()

    def _query() -> List[Dict[str, Any]]:
        response = (
            client.table("chat_sessions")
            .select("id, summary_updated_at")
            .eq("status", "active")
            .or_(
                "summary_updated_at.is.null,summary_updated_at.lt." + cutoff_iso
            )
            .limit(50)
            .execute()
        )
        return response.data or []

    return await asyncio.to_thread(_query)


async def _prune_old_messages(client, session_id: str, keep_limit: int) -> None:
    if keep_limit <= 0:
        return

    ids_to_trim = await _messages_to_trim(client, session_id, keep_limit)
    if not ids_to_trim:
        return

    timestamp = datetime.now(timezone.utc).isoformat()

    def _update() -> None:
        client.table("chat_messages").update({"deleted_at": timestamp}).in_("id", ids_to_trim).execute()

    await asyncio.to_thread(_update)


async def _messages_to_trim(client, session_id: str, keep_limit: int) -> List[str]:
    def _query() -> List[str]:
        response = (
            client.table("chat_messages")
            .select("id")
            .eq("session_id", session_id)
            .is_("deleted_at", None)
            .order("created_at", desc=True)
            .offset(keep_limit)
            .execute()
        )
        rows = response.data or []
        return [row["id"] for row in rows if "id" in row]

    return await asyncio.to_thread(_query)
