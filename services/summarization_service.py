"""Conversation summarization utilities for chat sessions."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import tiktoken
from openai import AsyncOpenAI

from config import get_settings
from services.supabase_client import get_supabase_client
from utils.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)
encoding = tiktoken.get_encoding("cl100k_base")

SUMMARY_MESSAGE_THRESHOLD = max(settings.summary_message_threshold, 1)
SUMMARY_MAX_INPUT_TOKENS = max(settings.summary_max_input_tokens, 512)
SUMMARY_MAX_OUTPUT_TOKENS = max(settings.summary_max_output_tokens, 128)
SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following WhatsApp conversation between Parcelo and a customer. "
    "Capture key facts, requests, commitments, and any follow-up items. Keep tone neutral and concise."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def maybe_generate_summary(session_id: str) -> Optional[str]:
    """Generate and store a session summary when enough new messages arrive."""

    supabase = get_supabase_client()
    session_record = await _fetch_session_metadata(supabase, session_id)
    if not session_record:
        return None

    last_summary_at = session_record.get("summary_updated_at")
    messages = await _fetch_messages_since(supabase, session_id, last_summary_at)
    if len(messages) < SUMMARY_MESSAGE_THRESHOLD:
        return None

    formatted_segments = _format_messages_for_summary(messages)
    if not formatted_segments:
        return None

    payload_text, token_count = _combine_segments_with_limit(formatted_segments)
    if token_count == 0:
        return None

    summary_text = await _run_summary_model(payload_text)
    if not summary_text:
        return None

    summary_tokens = len(encoding.encode(summary_text))
    await _store_summary(supabase, session_id, summary_text, summary_tokens)

    return summary_text


async def _fetch_session_metadata(client, session_id: str) -> Optional[Dict[str, Any]]:
    def _query() -> Optional[Dict[str, Any]]:
        response = (
            client.table("chat_sessions")
            .select("summary_updated_at")
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        return response.data if response.data else None

    return await asyncio.to_thread(_query)


async def _fetch_messages_since(
    client, session_id: str, last_summary_at: Optional[str]
) -> List[Dict[str, Any]]:
    def _query() -> List[Dict[str, Any]]:
        query = (
            client.table("chat_messages")
            .select("direction,message_type,text,media_url,created_at")
            .eq("session_id", session_id)
            .is_("deleted_at", None)
            .order("created_at")
        )
        if last_summary_at:
            query = query.gt("created_at", last_summary_at)
        response = query.execute()
        return response.data or []

    return await asyncio.to_thread(_query)


def _format_messages_for_summary(messages: List[Dict[str, Any]]) -> List[str]:
    formatted: List[str] = []
    for item in messages:
        direction = item.get("direction")
        prefix = "Customer" if direction == "inbound" else "Parcelo" if direction == "outbound" else "System"
        text = (item.get("text") or "").strip()
        if text:
            formatted.append(f"{prefix}: {text}")
            continue

        message_type = item.get("message_type") or "text"
        if message_type != "text":
            media_url = item.get("media_url")
            media_note = message_type.replace("_", " ").title()
            if media_url:
                formatted.append(f"{prefix}: {media_note} shared ({media_url})")
            else:
                formatted.append(f"{prefix}: {media_note} message")
    return formatted


def _combine_segments_with_limit(segments: List[str]) -> tuple[str, int]:
    combined: List[str] = []
    token_total = 0

    for segment in segments:
        tokens = len(encoding.encode(segment))
        if token_total + tokens > SUMMARY_MAX_INPUT_TOKENS:
            break
        combined.append(segment)
        token_total += tokens

    return "\n".join(combined), token_total


async def _run_summary_model(payload_text: str) -> Optional[str]:
    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": payload_text},
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages,
         
          
        )
    except Exception as exc:  # pragma: no cover - network issues
        logger.exception("Summary generation failed", extra={"session_id": payload_text[:32]})
        return None

    choice = response.choices[0] if response.choices else None
    if not choice or not choice.message or not choice.message.content:
        return None

    return choice.message.content.strip()


async def _store_summary(
    client, session_id: str, summary_text: str, token_count: int
) -> None:
    timestamp = _now_iso()

    def _insert() -> None:
        client.table("session_summaries").insert(
            {
                "session_id": session_id,
                "summary_text": summary_text,
                "token_count": token_count,
            }
        ).execute()

    def _update_session() -> None:
        client.table("chat_sessions").update(
            {
                "summary_updated_at": timestamp,
                "updated_at": timestamp,
            }
        ).eq("id", session_id).execute()

    await asyncio.gather(
        asyncio.to_thread(_insert),
        asyncio.to_thread(_update_session),
    )
