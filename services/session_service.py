"""Chat session management."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from services.supabase_client import get_supabase_client

SESSION_TTL_DAYS = 30
WA_WINDOW_HOURS = 24


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
            .eq("phone_number", phone_number)
            .order("created_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return _response_data(response)

    existing = await asyncio.to_thread(_lookup)
    if existing:
        if _is_session_expired(existing.get("expires_at")):
            await asyncio.to_thread(_close_session, client, existing["id"])
        else:
            return existing

    def _insert() -> Dict[str, Any]:
        now = _now()
        payload = {
            "customer_id": customer_id,
            "channel": "whatsapp",
            "phone_number": phone_number,
            "user_phone_e164": phone_number,
            "status": "active",
            "last_message_at": now.isoformat(),
            "last_inbound_at": now.isoformat(),
            "wa_window_expires_at": _window_deadline(now).isoformat(),
            "expires_at": _ttl_deadline(now).isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        response = client.table("chat_sessions").insert(payload, returning="representation").execute()
        data = _response_data(response)
        if isinstance(data, list):
            data = data[0] if data else None
        if data is None:
            raise RuntimeError("Failed to create chat session")
        return data

    created = await asyncio.to_thread(_insert)
    return created


async def update_session_last_message(
    session_id: str,
    *,
    direction: str,
    phone_number: Optional[str] = None,
) -> None:
    """Update session timestamps and TTL values."""

    client = get_supabase_client()

    def _update() -> None:
        now = _now()
        payload: Dict[str, Any] = {
            "last_message_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": _ttl_deadline(now).isoformat(),
        }

        if direction == "inbound":
            payload["last_inbound_at"] = now.isoformat()
            payload["wa_window_expires_at"] = _window_deadline(now).isoformat()
            if phone_number:
                payload["phone_number"] = phone_number
                payload["user_phone_e164"] = phone_number
        elif direction == "outbound":
            payload["last_outbound_at"] = now.isoformat()

        client.table("chat_sessions").update(payload).eq("id", session_id).execute()

    await asyncio.to_thread(_update)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ttl_deadline(now: datetime) -> datetime:
    return now + timedelta(days=SESSION_TTL_DAYS)


def _window_deadline(now: datetime) -> datetime:
    return now + timedelta(hours=WA_WINDOW_HOURS)


def _is_session_expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return False
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expires <= _now()


def _close_session(client, session_id: str) -> None:
    now = _now().isoformat()
    client.table("chat_sessions").update(
        {"status": "closed", "closed_at": now, "updated_at": now}
    ).eq("id", session_id).execute()


def _response_data(response: Any) -> Any:
    if response is None:
        return None
    data = getattr(response, "data", None)
    if data is not None:
        return data
    return response
