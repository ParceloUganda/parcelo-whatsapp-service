"""Luminous webhook endpoint implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from services.agent_runner import run_agent_workflow
from services.chat_service import (
    insert_inbound_message,
    insert_outbound_message,
    message_exists,
)
from services.customer_service import (
    resolve_customer_from_phone,
    update_customer_from_contact,
)
from services.event_service import (
    inbound_event_exists,
    mark_event_processed,
    store_inbound_event,
)
from services.idempotency_service import (
    check_idempotency_key,
    record_idempotency_key,
)
from services.luminous_client import send_whatsapp_message
from services.session_service import (
    get_or_create_chat_session,
    update_session_last_message,
)
from services.telegram_client import (
    notify_agent_error,
    notify_agent_response,
    notify_incoming_message,
)
from utils.logging import get_logger


router = APIRouter(prefix="/api/luminous", tags=["Luminous"])
logger = get_logger(__name__)


@router.post("/webhook")
async def luminous_webhook(request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Handle webhook events sent by Luminous."""

    headers = dict(request.headers)
    logger.info("Webhook invoked", extra={"headers": headers})

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:  # pragma: no cover - FastAPI handles JSON errors
        logger.exception("Failed to parse webhook payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    logger.debug("Webhook payload", extra={"payload": payload})

    event, data, timestamp = normalize_payload(payload)
    if not event or data is None:
        raise HTTPException(status_code=400, detail="Invalid payload: missing event or data")

    phone_number = extract_phone_number(data)
    precomputed_message: Optional[MessageData] = None

    if event == "message.received":
        precomputed_message = extract_message_data(data)
        if precomputed_message.phone_number:
            phone_number = phone_number or precomputed_message.phone_number

    idempotency_key = build_idempotency_key(event, data, timestamp, phone_number)
    logger.debug("Idempotency key", extra={"key": idempotency_key})

    if await check_idempotency_key(idempotency_key, "wa_webhook"):
        logger.info("Duplicate event skipped", extra={"key": idempotency_key})
        return {"success": True, "message": "Already processed"}

    if await inbound_event_exists(idempotency_key):
        logger.info("Duplicate inbound event skipped", extra={"dedupe_key": idempotency_key})
        return {"success": True, "message": "Already processed"}

    await record_idempotency_key(idempotency_key, "wa_webhook", payload)

    event_id = await store_inbound_event(
        phone_number=phone_number,
        wa_message_id=data.get("id"),
        event_type=resolve_event_type(event),
        raw_payload=payload,
        dedupe_key=idempotency_key,
        occurred_at=timestamp,
    )

    try:
        if event == "message.received":
            await handle_message_received(
                data,
                event_id,
                background_tasks,
                precomputed_message=precomputed_message,
            )
        elif event == "message.sent":
            logger.debug("Message sent event", extra={"data": data})
        elif event == "message.status.update":
            logger.debug("Status update event", extra={"data": data})
        else:
            logger.info("Unhandled event type", extra={"event": event})
    finally:
        if event_id:
            await mark_event_processed(event_id)

    return {"success": True}


# ---------------------------------------------------------------------------
# Payload Normalisation
# ---------------------------------------------------------------------------

def normalize_payload(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """Normalise WhatsApp/Luminous payload structures."""

    event = payload.get("event")
    data = payload.get("data")
    timestamp = payload.get("timestamp")

    # Handle WhatsApp Business API format (entry.changes[0].value)
    if not data and isinstance(payload.get("entry"), list):
        entry = payload["entry"][0]
        change = entry.get("changes", [None])[0] if isinstance(entry, dict) else None
        value = change.get("value") if isinstance(change, dict) else None
        if value:
            data = value
            if not event:
                event = "message.received"
            first_message = value.get("messages", [None])[0] if isinstance(value.get("messages"), list) else None
            timestamp = first_message.get("timestamp") if isinstance(first_message, dict) else timestamp

    # Handle nested data structures { data: {...} }
    if isinstance(data, dict) and set(data.keys()) == {"data"}:
        data = data.get("data")

    # Handle change format { value: {...}, field: "messages" }
    if isinstance(data, dict) and {"value", "field"}.issubset(data.keys()):
        data = data.get("value")

    return event, data, timestamp


def build_idempotency_key(
    event: str,
    data: Dict[str, Any],
    timestamp: Optional[str],
    phone_number: Optional[str],
) -> str:
    message_id = (
        data.get("id")
        or data.get("message_id")
        or data.get("messageId")
        or (
            data.get("messages", [None])[0].get("id")
            if isinstance(data.get("messages"), list) and data["messages"]
            else None
        )
        or (
            data.get("statuses", [None])[0].get("id")
            if isinstance(data.get("statuses"), list) and data["statuses"]
            else None
        )
        or "no-id"
    )
    phone = phone_number or "unknown"
    ts = timestamp or data.get("timestamp") or "unknown"
    return f"{event}-{message_id}-{phone}-{ts}"


def extract_phone_number(data: Dict[str, Any]) -> Optional[str]:
    """Derive phone number from various WhatsApp payload shapes."""

    candidates = [
        data.get("from"),
        data.get("phone"),
        data.get("phoneNumber"),
        data.get("phone_number"),
    ]

    for candidate in candidates:
        if candidate:
            return candidate

    messages = data.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            msg_candidates = [
                message.get("from"),
                message.get("phone"),
                message.get("phoneNumber"),
                message.get("phone_number"),
            ]
            for candidate in msg_candidates:
                if candidate:
                    return candidate

    contacts = data.get("contacts")
    if isinstance(contacts, list) and contacts:
        contact = contacts[0]
        if isinstance(contact, dict):
            wa_id = contact.get("wa_id")
            if wa_id:
                return wa_id if wa_id.startswith("+") else f"+{wa_id.lstrip('+')}"

    statuses = data.get("statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            recipient = status.get("recipient_id") or status.get("recipientId")
            if recipient:
                return recipient if str(recipient).startswith("+") else f"+{str(recipient).lstrip('+')}"

    return None


def resolve_event_type(event: str) -> str:
    if "status" in event:
        return "status"
    if "sent" in event:
        return "message"
    if "message" in event:
        return "message"
    return "unknown"


# ---------------------------------------------------------------------------
# Message Handling
# ---------------------------------------------------------------------------

@dataclass
class MessageData:
    phone_number: Optional[str]
    message_text: str
    message_type: str
    wa_message_id: Optional[str]
    wa_timestamp: str
    contact_name: str
    media_url: Optional[str] = None
    media_mime_type: Optional[str] = None


def extract_message_data(data: Dict[str, Any]) -> MessageData:
    message = data
    if isinstance(data.get("messages"), list) and data["messages"]:
        message = data["messages"][0]
        if isinstance(data.get("contacts"), list) and data["contacts"]:
            message["contact"] = data["contacts"][0]

    phone_number = (
        message.get("from")
        or message.get("phone")
        or message.get("phoneNumber")
        or message.get("phone_number")
        or data.get("from")
    )

    message_text = (
        (message.get("text") or {}).get("body")
        or (message.get("message") or {}).get("body")
        or message.get("message")
        or message.get("text")
        or ""
    )

    message_type = message.get("type") or message.get("message_type") or "text"
    wa_message_id = (
        message.get("id")
        or message.get("message_id")
        or message.get("messageId")
        or message.get("wa_message_id")
    )

    wa_timestamp = parse_timestamp(
        message.get("timestamp")
        or message.get("created_at")
        or data.get("timestamp")
    )

    contact = message.get("contact", {}) if isinstance(message, dict) else {}
    contact_name = (
        contact.get("profile", {}).get("name")
        or contact.get("name")
        or data.get("contact", {}).get("name")
        or "Customer"
    )

    media_url = None
    media_mime_type = None
    if message_type == "image" and message.get("image"):
        media_url = message["image"].get("link")
        media_mime_type = message["image"].get("mime_type")

    return MessageData(
        phone_number=phone_number,
        message_text=message_text,
        message_type=message_type,
        wa_message_id=wa_message_id,
        wa_timestamp=wa_timestamp,
        contact_name=contact_name,
        media_url=media_url,
        media_mime_type=media_mime_type,
    )


def parse_timestamp(value: Optional[str]) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, str) and value.isdigit():
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
        except ValueError:
            return datetime.now(timezone.utc).isoformat()
    return value


async def handle_message_received(
    data: Dict[str, Any],
    event_id: Optional[str],
    background_tasks: BackgroundTasks,
    *,
    precomputed_message: Optional[MessageData] = None,
) -> None:
    message_data = precomputed_message or extract_message_data(data)

    if not message_data.phone_number or not message_data.wa_message_id:
        logger.error("Missing phone or message ID", extra={"data": data})
        return

    if await message_exists(message_data.wa_message_id):
        logger.info("Message already processed", extra={"wa_message_id": message_data.wa_message_id})
        return

    await notify_incoming_message(
        message_data.phone_number,
        message_data.message_text,
        message_data.contact_name,
    )

    customer = await resolve_customer_from_phone(
        message_data.phone_number,
        display_name=message_data.contact_name,
        whatsapp_id=message_data.wa_message_id,
    )

    await update_customer_from_contact(
        customer_id=customer["customer_id"],
        display_name=message_data.contact_name,
        whatsapp_id=message_data.wa_message_id,
    )

    session = await get_or_create_chat_session(customer["customer_id"], message_data.phone_number)

    await insert_inbound_message(
        session_id=session["id"],
        customer_id=customer["customer_id"],
        message_type=message_data.message_type,
        text=message_data.message_text,
        payload=data,
        wa_message_id=message_data.wa_message_id,
        wa_status="delivered",
        wa_timestamp=message_data.wa_timestamp,
        media_url=message_data.media_url,
        media_mime_type=message_data.media_mime_type,
    )

    await update_session_last_message(session["id"])

    background_tasks.add_task(
        process_with_agent,
        customer_id=customer["customer_id"],
        session_id=session["id"],
        phone_number=message_data.phone_number,
        customer_name=message_data.contact_name,
        message_text=message_data.message_text,
    )


async def process_with_agent(
    *,
    customer_id: str,
    session_id: str,
    phone_number: str,
    customer_name: str,
    message_text: str,
) -> None:
    try:
        agent_output = await run_agent_workflow(
            message_text=message_text,
            customer_id=customer_id,
            session_id=session_id,
            phone_number=phone_number,
            customer_name=customer_name,
        )
        response_text = agent_output.get("response_text") or "Thank you for your message."

        send_result = await send_whatsapp_message(phone_number, response_text)
        wa_message_id = send_result.get("message_id")

        await insert_outbound_message(
            session_id=session_id,
            customer_id=customer_id,
            text=response_text,
            wa_message_id=wa_message_id,
            metadata={"agent": agent_output},
        )

        await notify_agent_response(
            phone_number,
            response_text,
            agent_output.get("intent"),
            customer_name,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Agent processing failed")
        await notify_agent_error(phone_number, message_text, str(exc), customer_name)
