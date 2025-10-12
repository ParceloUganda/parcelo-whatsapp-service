"""Customer resolution utilities."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from services.supabase_client import get_supabase_client


def _normalize_phone(phone: str) -> str:
    return phone if phone.startswith("+") else f"+{phone}"


async def resolve_customer_from_phone(
    phone_number: str,
    *,
    display_name: Optional[str] = None,
    whatsapp_id: Optional[str] = None,
) -> dict:
    """Find or create customer by phone number."""

    client = get_supabase_client()
    normalized_phone = _normalize_phone(phone_number)

    def _lookup() -> Optional[dict]:
        response = (
            client.table("customers")
            .select("id, profile_id, phone_number, display_name, whatsapp_id")
            .eq("phone_number", normalized_phone)
            .maybe_single()
            .execute()
        )
        return response.data

    existing = await asyncio.to_thread(_lookup)
    if existing:
        return {
            "customer_id": existing["id"],
            "profile_id": existing.get("profile_id"),
            "phone_number": existing.get("phone_number", normalized_phone),
            "display_name": existing.get("display_name") or display_name or "Customer",
            "whatsapp_id": existing.get("whatsapp_id"),
            "is_new_customer": False,
        }

    def _insert() -> dict:
        payload = {
            "phone_number": normalized_phone,
            "display_name": display_name or "Customer",
            "whatsapp_id": whatsapp_id,
            "profile_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        response = (
            client.table("customers")
            .insert([payload])
            .select("id, profile_id, phone_number, display_name, whatsapp_id")
            .single()
            .execute()
        )
        return response.data

    created = await asyncio.to_thread(_insert)
    return {
        "customer_id": created["id"],
        "profile_id": created.get("profile_id"),
        "phone_number": created.get("phone_number", normalized_phone),
        "display_name": created.get("display_name") or "Customer",
        "whatsapp_id": created.get("whatsapp_id"),
        "is_new_customer": True,
    }


async def update_customer_from_contact(
    customer_id: str,
    *,
    display_name: Optional[str] = None,
    whatsapp_id: Optional[str] = None,
) -> None:
    """Update customer metadata from contact info."""

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if display_name:
        updates["display_name"] = display_name
    if whatsapp_id:
        updates["whatsapp_id"] = whatsapp_id

    client = get_supabase_client()

    def _update() -> None:
        client.table("customers").update(updates).eq("id", customer_id).execute()

    await asyncio.to_thread(_update)
