"""Chat session management."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from services.supabase_client import get_supabase_client


async def get_or_create_chat_session(customer_id: str, phone_number: str) -> Dict[str, Any]:
    """Fetch active session or create new one for WhatsApp channel."""

    client = get_supabase_client()

    def _lookup() -> Dict[str, Any] | None:
        response = (
            client.table("chat_sessions")
            .select("*")
            .eq("customer_id", customer_id)
            .eq("channel", "whatsapp")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return response.data

    existing = await asyncio.to_thread(_lookup)
    if existing:
        return existing

    def _insert() -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "customer_id": customer_id,
            "channel": "whatsapp",
            "phone_number": phone_number,
            "user_phone_e164": phone_number,
            "status": "active",
            "last_message_at": now,
            "created_at": now,
        }
        response = (
            client.table("chat_sessions")
            .insert([payload])
            .select("*")
            .single()
            .execute()
        )
        return response.data

    created = await asyncio.to_thread(_insert)
    return created


async def update_session_last_message(session_id: str) -> None:
    """Update session timestamps."""

    client = get_supabase_client()

    def _update() -> None:
        now = datetime.now(timezone.utc).isoformat()
        client.table("chat_sessions").update(
            {"last_message_at": now, "updated_at": now}
        ).eq("id", session_id).execute()

    await asyncio.to_thread(_update)
