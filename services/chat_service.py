"""Chat message persistence utilities."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.supabase_client import get_supabase_client


async def message_exists(wa_message_id: str) -> bool:
    """Return True if a chat message already exists for given WhatsApp ID."""

    client = get_supabase_client()

    def _lookup() -> Optional[Dict[str, Any]]:
        response = (
            client.table("chat_messages")
            .select("id")
            .eq("wa_message_id", wa_message_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    try:
        data = await asyncio.to_thread(_lookup)
    except Exception as exc:  # pragma: no cover - Supabase failure fallback
        logger.warning("Failed to check chat message existence", exc_info=exc)
        data = None

    return data is not None


async def insert_inbound_message(
    *,
    session_id: str,
    customer_id: str,
    message_type: str,
    text: str,
    payload: Dict[str, Any],
    wa_message_id: str,
    wa_status: str,
    wa_timestamp: str,
    media_url: Optional[str] = None,
    media_mime_type: Optional[str] = None,
) -> str:
    """Insert inbound chat message and return new id."""

    client = get_supabase_client()

    def _insert() -> str:
        row = {
            "session_id": session_id,
            "customer_id": customer_id,
            "direction": "inbound",
            "message_type": message_type,
            "text": text,
            "media_url": media_url,
            "media_mime_type": media_mime_type,
            "payload": payload,
            "wa_message_id": wa_message_id,
            "wa_status": wa_status,
            "wa_timestamp": wa_timestamp,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.table("chat_messages").insert([row]).execute()
        data = response.data or []
        record = data[0] if data else None
        if not record or "id" not in record:
            raise RuntimeError("chat message insert did not return id")
        return record["id"]

    return await asyncio.to_thread(_insert)


async def insert_outbound_message(
    *,
    session_id: str,
    customer_id: str,
    text: str,
    wa_message_id: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist outbound chat message record."""

    client = get_supabase_client()

    def _insert() -> None:
        payload = {
            "session_id": session_id,
            "customer_id": customer_id,
            "direction": "outbound",
            "message_type": "text",
            "text": text,
            "wa_message_id": wa_message_id,
            "wa_status": "sent" if wa_message_id else "sent",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": metadata or {},
        }
        client.table("chat_messages").insert([payload]).execute()

    await asyncio.to_thread(_insert)
