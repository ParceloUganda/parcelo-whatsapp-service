"""Idempotency key storage via Supabase."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from postgrest import APIError

from services.supabase_client import get_supabase_client
from utils.logging import get_logger


logger = get_logger(__name__)


async def record_idempotency_key(key: str, source: str, request_payload: dict) -> None:
    """Persist idempotency key in Supabase."""

    client = get_supabase_client()
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    def _insert() -> None:
        client.table("idempotency_keys").insert([
            {
                "key": key,
                "source": source,
                "request_hash": json.dumps(request_payload),
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        ]).execute()

    try:
        await asyncio.to_thread(_insert)
    except APIError as exc:  # pragma: no cover - duplicate or other API error
        if exc.message and "duplicate key value" in exc.message:
            logger.info("Idempotency key already exists", extra={"key": key})
        else:
            logger.warning("Failed to record idempotency key", exc_info=exc)
    except Exception as exc:  # pragma: no cover - Supabase failure fallback
        logger.warning("Failed to record idempotency key", exc_info=exc)


async def check_idempotency_key(key: str, source: str) -> bool:
    """Return True if key exists for source."""

    client = get_supabase_client()

    def _select() -> Optional[dict]:
        response = (
            client.table("idempotency_keys")
            .select("key")
            .eq("key", key)
            .eq("source", source)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    try:
        data = await asyncio.to_thread(_select)
    except Exception as exc:  # pragma: no cover - Supabase failure fallback
        logger.warning("Failed to check idempotency key", exc_info=exc)
        data = None

    return bool(data)
