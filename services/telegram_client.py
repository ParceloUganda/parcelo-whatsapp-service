"""Telegram notification helpers."""

import httpx

from config import get_settings
from utils.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


def _is_enabled() -> bool:
    return bool(
        settings.telegram_bot_token
        and settings.telegram_chat_id
        and settings.telegram_notifications_enabled
    )


async def _post_message(text: str) -> bool:
    if not _is_enabled():
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
    except Exception as exc:  # pragma: no cover - network failure fallback
        logger.warning("Telegram notification failed", exc_info=exc)
        return False


async def notify_incoming_message(phone_number: str, message: str, customer_name: str | None) -> None:
    text = (
        "📩 <b>MESSAGE RECEIVED</b>\n\n"
        f"<b>From:</b> {customer_name or 'Customer'} ({phone_number})\n"
        f"<b>Message:</b> {message[:300]}"
    )
    await _post_message(text)


async def notify_agent_response(phone_number: str, response: str, intent: str | None, customer_name: str | None) -> None:
    text = (
        "✅ <b>AGENT RESPONDED</b>\n\n"
        f"<b>Customer:</b> {customer_name or 'Customer'} ({phone_number})\n"
        f"<b>Intent:</b> {intent or 'unknown'}\n"
        f"<b>Response:</b> {response[:300]}"
    )
    await _post_message(text)


async def notify_agent_error(phone_number: str, message: str, error: str, customer_name: str | None) -> None:
    text = (
        "❌ <b>AGENT ERROR</b>\n\n"
        f"<b>Customer:</b> {customer_name or 'Customer'} ({phone_number})\n"
        f"<b>Message:</b> {message[:300]}\n"
        f"<b>Error:</b> {error[:300]}"
    )
    await _post_message(text)
