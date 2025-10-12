"""Client for sending WhatsApp messages via Luminous API."""

import httpx

from config import get_settings

settings = get_settings()


async def send_whatsapp_message(phone: str, message: str) -> dict:
    """Send WhatsApp message via Luminous API."""

    payload = {"phone": phone if phone.startswith("+") else f"+{phone}", "message": message}
    headers = {
        "Authorization": f"Bearer {settings.luminous_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{settings.luminous_api_url}/api/send", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        message_id = (
            data.get("data", {})
            .get("messages", [{}])[0]
            .get("id")
        )
        return {"success": True, "message_id": message_id, "raw": data}
