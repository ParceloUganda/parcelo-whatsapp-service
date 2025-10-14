"""Luminous webhook endpoint implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request

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
from services.media_service import (
    MediaDownloadDisabled,
    fetch_media_metadata,
    download_media_to_storage,
    process_caption_if_needed,
    process_transcription_if_needed,
    record_chat_media,
)
from services.session_service import (
    get_or_create_chat_session,
    update_session_last_message,
)
from services.embedding_service import generate_message_embedding
from services.summarization_service import maybe_generate_summary
from services.telegram_client import (
    notify_agent_error,
    notify_agent_response,
    notify_incoming_message,
)
from config import get_settings
from utils.logging import get_logger


router = APIRouter(prefix="/api/luminous", tags=["Luminous"])
logger = get_logger(__name__)
settings = get_settings()

_session_locks: dict[str, asyncio.Lock] = {}
_session_locks_guard = asyncio.Lock()


def _serialize_for_log(value: Any, *, limit: int = 4000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > limit:
        return f"{text[:limit]}...(truncated)"
    return text


EXAMPLE_WEBHOOK_PAYLOAD: Dict[str, Any] = {
    "event": "message.received",
    "data": {
        "id": "sample-message-id",
        "from": "+256700000000",
        "messages": [
            {
                "id": "sample-message-id",
                "from": "+256700000000",
                "timestamp": "1700000000",
                "type": "text",
                "text": {"body": "Hello Parcelo!"},
            }
        ],
    },
    "timestamp": "2025-10-14T18:56:18Z",
}


@router.post("/webhook")
async def luminous_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(..., example=EXAMPLE_WEBHOOK_PAYLOAD),
) -> Dict[str, Any]:
    """Handle webhook events sent by Luminous."""

    headers = dict(request.headers)
    logger.info("Webhook invoked", extra={"headers": headers})

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


def _resolve_message_container(payload: Dict[str, Any]) -> Dict[str, Any]:
    root = payload
    if isinstance(root.get("body"), dict):
        root = root["body"].get("data") or root["body"]
    if isinstance(root, dict) and set(root.keys()) == {"data"}:
        root = root.get("data")
    if isinstance(root, dict) and {"value", "field"}.issubset(root.keys()):
        root = root.get("value")
    return root if isinstance(root, dict) else {}


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


async def _get_session_lock(session_id: str) -> asyncio.Lock:
    async with _session_locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[session_id] = lock
        return lock


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
    message_container = _resolve_message_container(data)
    message_list = message_container.get("messages")
    message = message_list[0] if isinstance(message_list, list) and message_list else message_container

    contacts = message_container.get("contacts")
    if isinstance(contacts, list) and contacts:
        message["contact"] = contacts[0]

    phone_number = (
        message.get("from")
        or message_container.get("from")
        or message.get("phone")
        or message.get("phoneNumber")
        or message.get("phone_number")
        or extract_phone_number(message_container)
    )
    if phone_number and not str(phone_number).startswith("+"):
        phone_number = f"+{str(phone_number).lstrip('+')}"

    message_text = (
        (message.get("text") or {}).get("body")
        or message.get("body")
        or message.get("caption")
        or (message.get("image") or {}).get("caption")
        or (message.get("document") or {}).get("caption")
        or ""
    )

    message_type = message.get("type") or "text"
    wa_message_id = message.get("id")

    wa_timestamp = parse_timestamp(
        message.get("timestamp")
        or message_container.get("timestamp")
    )

    contact = message.get("contact", {}) if isinstance(message, dict) else {}
    contact_name = (
        contact.get("profile", {}).get("name")
        or contact.get("name")
        or "Customer"
    )

    media_url = None
    media_mime_type = None
    if message_type == "image" and message.get("image"):
        media_url = message["image"].get("url") or message["image"].get("link")
        media_mime_type = message["image"].get("mime_type")
    elif message_type == "audio" and message.get("audio"):
        media_url = message["audio"].get("url")
        media_mime_type = message["audio"].get("mime_type")
    elif message_type == "video" and message.get("video"):
        media_url = message["video"].get("url")
        media_mime_type = message["video"].get("mime_type")
    elif message_type == "document" and message.get("document"):
        media_url = message["document"].get("url")
        media_mime_type = message["document"].get("mime_type")

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
    logger.info(
        "Inbound message parsed %s",
        _serialize_for_log(
            {
                "wa_message_id": message_data.wa_message_id,
                "phone_number": message_data.phone_number,
                "message_type": message_data.message_type,
                "has_media_url": bool(message_data.media_url),
                "raw_message_keys": list(data.keys()) if isinstance(data, dict) else None,
            }
        ),
    )
    if message_data.message_type != "text":
        logger.debug(
            "Inbound raw payload %s",
            _serialize_for_log({
                "wa_message_id": message_data.wa_message_id,
                "payload": data,
            }),
        )

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

    message_id = await insert_inbound_message(
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

    await update_session_last_message(
        session["id"],
        direction="inbound",
        phone_number=message_data.phone_number,
    )

    background_tasks.add_task(
        generate_message_embedding,
        message_id,
        message_data.message_text,
    )
    background_tasks.add_task(maybe_generate_summary, session["id"])

    if settings.enable_media_download and message_data.message_type in {"image", "audio", "document"}:
        background_tasks.add_task(
            process_media_message,
            message_id=message_id,
            message_type=message_data.message_type,
            wa_media_id=_extract_media_id(data),
            mime_type=message_data.media_mime_type,
        )

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
    lock = await _get_session_lock(session_id)
    if lock.locked():
        logger.info(
            "Waiting for session lock",
            extra={"session_id": session_id, "customer_id": customer_id},
        )

    async with lock:
        logger.debug(
            "Session lock acquired",
            extra={"session_id": session_id, "customer_id": customer_id},
        )
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

            message_id = await insert_outbound_message(
                session_id=session_id,
                customer_id=customer_id,
                text=response_text,
                wa_message_id=wa_message_id,
                metadata={"agent": agent_output},
            )

            await update_session_last_message(session_id, direction="outbound")

            # Schedule embedding and summary updates
            await asyncio.gather(
                generate_message_embedding(message_id, response_text),
                maybe_generate_summary(session_id),
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
        finally:
            logger.debug(
                "Session lock released",
                extra={"session_id": session_id, "customer_id": customer_id},
            )


async def process_media_message(
    *,
    message_id: str,
    message_type: str,
    wa_media_id: Optional[str],
    mime_type: Optional[str],
) -> None:
    if not wa_media_id:
        logger.warning("Missing wa_media_id for media message", extra={"message_id": message_id})
        return

    try:
        metadata = await fetch_media_metadata(wa_media_id)
        logger.info(
            "Fetched media metadata %s",
            _serialize_for_log(
                {
                    "message_id": message_id,
                    "wa_media_id": wa_media_id,
                    "metadata": metadata,
                }
            ),
        )
    except MediaDownloadDisabled:
        logger.debug("Media download disabled; skipping", extra={"message_id": message_id})
        return
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to fetch media metadata", extra={"wa_media_id": wa_media_id})
        return

    if not metadata:
        logger.warning(
            "Missing metadata for media %s",
            _serialize_for_log({"message_id": message_id, "wa_media_id": wa_media_id}),
        )
        return

    download_url = metadata.get("url")
    resolved_mime_type = metadata.get("mime_type") or mime_type or "application/octet-stream"

    try:
        result = await download_media_to_storage(
            message_id=message_id,
            wa_media_id=wa_media_id,
            download_url=download_url,
            mime_type=resolved_mime_type,
        )
        logger.info(
            "Media download result %s",
            _serialize_for_log(
                {
                    "message_id": message_id,
                    "wa_media_id": wa_media_id,
                    "mime_type": resolved_mime_type,
                    "downloaded": bool(result),
                }
            ),
        )
    except MediaDownloadDisabled:
        logger.debug("Media download disabled mid-process", extra={"message_id": message_id})
        return
    except Exception:  # pragma: no cover - defensive
        logger.exception("Media download failed", extra={"wa_media_id": wa_media_id})
        return

    if not result:
        return

    caption: Optional[str] = None
    transcript: Optional[str] = None

    try:
        caption = await process_caption_if_needed(result)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Image captioning step failed", extra={"message_id": message_id})

    try:
        transcript = await process_transcription_if_needed(result)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Audio transcription step failed", extra={"message_id": message_id})

    await record_chat_media(result, caption=caption, transcript=transcript)


def _extract_media_id(data: Dict[str, Any]) -> Optional[str]:
    container = _resolve_message_container(data)
    message = container
    if isinstance(container.get("messages"), list) and container["messages"]:
        message = container["messages"][0]
    else:
        message = container

    if isinstance(message, dict):
        for key in ("image", "audio", "video", "document"):
            media = message.get(key)
            if isinstance(media, dict):
                media_id = media.get("id")
                if media_id:
                    return media_id
    if isinstance(container.get("messages"), list):
        for entry in container["messages"]:
            if isinstance(entry, dict):
                for key in ("image", "audio", "video", "document"):
                    media = entry.get(key)
                    if isinstance(media, dict) and media.get("id"):
                        return media.get("id")
    return None
