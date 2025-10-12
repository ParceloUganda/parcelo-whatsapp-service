"""Inbound event persistence."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from postgrest import APIError

from services.supabase_client import get_supabase_client


async def store_inbound_event(
    *,
    phone_number: Optional[str],
    wa_message_id: Optional[str],
    event_type: str,
    raw_payload: Dict[str, Any],
    dedupe_key: str,
    occurred_at: Optional[str] = None,
) -> Optional[str]:
    """Insert a record into wa_inbound_events and return new id."""

    client = get_supabase_client()

    def _insert() -> Optional[str]:
        try:
            response = (
                client.table("wa_inbound_events")
                .insert(
                    [
                        {
                            "from_phone_e164": phone_number,
                            "wa_message_id": wa_message_id,
                            "event_type": event_type,
                            "raw": raw_payload,
                            "processed": False,
                            "dedupe_key": dedupe_key,
                            "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
                        }
                    ]
                )
                .execute()
            )
            data = response.data or []
            record = data[0] if data else None
            return record.get("id") if record else None
        except APIError as exc:
            if exc.message and "duplicate key value" in exc.message:
                existing = (
                    client.table("wa_inbound_events")
                    .select("id")
                    .eq("dedupe_key", dedupe_key)
                    .limit(1)
                    .execute()
                )
                data = existing.data or []
                record = data[0] if data else None
                return record.get("id") if record else None
            raise

    return await asyncio.to_thread(_insert)


async def mark_event_processed(event_id: str) -> None:
    """Mark inbound event as processed."""

    client = get_supabase_client()

    def _update() -> None:
        client.table("wa_inbound_events").update(
            {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", event_id).execute()

    await asyncio.to_thread(_update)


async def inbound_event_exists(dedupe_key: str) -> bool:
    """Check whether an inbound event already exists for given dedupe key."""

    client = get_supabase_client()

    def _lookup() -> Optional[Dict[str, Any]]:
        response = (
            client.table("wa_inbound_events")
            .select("id")
            .eq("dedupe_key", dedupe_key)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    try:
        data = await asyncio.to_thread(_lookup)
    except APIError as exc:  # pragma: no cover - log and continue
        # Most likely a permissions issue; treat as not found to avoid duplicates being blocked incorrectly
        return False
    except Exception:
        return False

    return data is not None
