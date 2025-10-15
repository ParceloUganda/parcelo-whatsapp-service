"""Simple OpenAI-powered agent workflow with sliding window context."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import tiktoken
from openai import AsyncOpenAI

from config import get_settings
from services.embedding_service import fetch_session_recall
from services.supabase_client import get_supabase_client
from utils.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)
encoding = tiktoken.get_encoding("cl100k_base")

WINDOW_SIZE = max(settings.llm_window_size, 1)
MAX_PROMPT_TOKENS = max(settings.llm_max_prompt_tokens, 1024)
OUTPUT_BUFFER_TOKENS = max(settings.llm_output_buffer_tokens, 128)

BASE_SYSTEM_PROMPT = (
    "You are ParceloBot, a helpful WhatsApp assistant for Parcelo Uganda. "
    "Provide concise, friendly answers. Offer to help with price quotes, order tracking, payments, "
    "and general questions. Keep tone warm and professional. Please don't repeat the person's names and number or what you do. "
    " Avoid informal language or tone."
    "You will want to have a personality that is friendly but professional."
)


async def run_agent_workflow(
    *,
    message_text: str,
    customer_id: str,
    session_id: str,
    phone_number: str,
    customer_name: str | None = None,
) -> Dict[str, Any]:
    """Run a conversational agent call with cached summary and sliding window context."""

    messages, token_usage = await build_prompt_messages(
        session_id=session_id,
        customer_name=customer_name,
        phone_number=phone_number,
        latest_user_text=message_text,
    )

    # Ensure the final user message is current even if cached context missed it
    appended_user = {
        "role": "user",
        "content": format_user_context(
            customer_name=customer_name,
            phone_number=phone_number,
            message_text=message_text,
        ),
    }
    if not messages or messages[-1]["role"] != "user":
        messages.append(appended_user)
    else:
        messages[-1] = appended_user

    try:
        response = await client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages,
            # max_tokens=MAX_PROMPT_TOKENS + OUTPUT_BUFFER_TOKENS,
       
        )
        reply = response.choices[0].message.content if response.choices else ""
    except Exception as exc:  # pragma: no cover - network failure safeguard
        logger.exception("OpenAI agent call failed")
        reply = (
            "I'm sorry, I'm having trouble responding right now. Please try again in a moment or "
            "type 'agent' to talk with a human."
        )

    return {
        "intent": "general",
        "response_text": reply.strip() or "Thank you for your message!",
        "action": None,
        "metadata": {
            "model": "gpt-5-nano",
            "customer_id": customer_id,
            "session_id": session_id,
            "prompt_tokens": token_usage.get("prompt_tokens"),
            "window_size": token_usage.get("window_size"),
            "summary_included": token_usage.get("summary_included"),
            "recall_included": token_usage.get("recall_included"),
            "recall_count": token_usage.get("recall_count"),
        },
    }


def format_user_context(*, customer_name: Optional[str], phone_number: str, message_text: str) -> str:
    return (
        f"Customer: {customer_name or 'Customer'}\n"
        f"Phone: {phone_number}\n"
        f"Message: {message_text}"
    )


async def build_prompt_messages(
    *, session_id: str, customer_name: Optional[str], phone_number: str, latest_user_text: str
) -> tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Build chat-completion messages using stored summaries and recent turns."""

    client = get_supabase_client()

    summary_text = await _fetch_latest_summary(client, session_id)
    recent_messages = await _fetch_recent_messages(client, session_id, WINDOW_SIZE)

    messages: List[Dict[str, str]] = [{"role": "system", "content": BASE_SYSTEM_PROMPT}]
    summary_included = False
    if summary_text:
        messages.append({"role": "system", "content": f"Conversation summary:\n{summary_text}"})
        summary_included = True

    recall_messages: List[Dict[str, str]] = []
    recall_count = 0
    if settings.enable_vector_recall and latest_user_text.strip() and settings.embeddings_recall_limit > 0:
        recall_rows = await fetch_session_recall(
            session_id,
            latest_user_text,
            limit=settings.embeddings_recall_limit,
            min_similarity=settings.embeddings_min_similarity,
        )
        recall_count = len(recall_rows)
        formatted = _format_recall_rows(recall_rows)
        if formatted:
            recall_messages.append({"role": "system", "content": formatted})
            messages.extend(recall_messages)

    for item in recent_messages:
        role = _map_direction_to_role(item.get("direction"))
        if not role:
            continue
        content = _format_message_content(item)
        if content:
            messages.append({"role": role, "content": content})

    recall_indices = [idx for idx, msg in enumerate(messages) if msg in recall_messages]
    prompt_tokens = _ensure_token_budget(messages, recall_indices)
    recall_included = any(idx < len(messages) and messages[idx] in recall_messages for idx in recall_indices)

    return messages, {
        "prompt_tokens": prompt_tokens,
        "window_size": len(recent_messages),
        "summary_included": summary_included,
        "recall_included": recall_included,
        "recall_count": recall_count if recall_included else 0,
    }


async def _fetch_latest_summary(client, session_id: str) -> Optional[str]:
    def _query() -> Optional[str]:
        response = (
            client.table("session_summaries")
            .select("summary_text")
            .eq("session_id", session_id)
            .order("updated_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        data = _coerce_response_data(response, default={})
        if isinstance(data, list):
            data = data[0] if data else {}
        return data.get("summary_text") if isinstance(data, dict) else None

    return await asyncio.to_thread(_query)


async def _fetch_recent_messages(client, session_id: str, limit: int) -> List[Dict[str, Any]]:
    def _query() -> List[Dict[str, Any]]:
        response = (
            client.table("chat_messages")
            .select("direction,message_type,text,media_url,media_mime_type,created_at")
            .eq("session_id", session_id)
            .is_("deleted_at", None)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        data = _coerce_response_data(response, default=[])
        if isinstance(data, dict):
            data = [data]
        return list(reversed(data))

    return await asyncio.to_thread(_query)


def _coerce_response_data(response: Any, default: Any) -> Any:
    if response is None:
        return default
    data = getattr(response, "data", None)
    if data is None:
        return default
    return data


def _map_direction_to_role(direction: Optional[str]) -> Optional[str]:
    if direction == "inbound":
        return "user"
    if direction == "outbound":
        return "assistant"
    if direction == "system":
        return "system"
    return None


def _format_message_content(message: Dict[str, Any]) -> str:
    text = (message.get("text") or "").strip()
    message_type = message.get("message_type") or "text"

    if text:
        return text

    if message_type != "text":
        media_url = message.get("media_url")
        media_note = message_type.replace("_", " ").title()
        if media_url:
            return f"[{media_note} shared: {media_url}]"
        return f"[{media_note} message]"

    return ""


def _count_tokens(messages: List[Dict[str, str]]) -> int:
    total = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            total += len(encoding.encode(content))
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content") or ""
                    total += len(encoding.encode(str(text)))
                else:
                    total += len(encoding.encode(str(part)))
        else:
            total += len(encoding.encode(str(content)))
    return total


def _ensure_token_budget(messages: List[Dict[str, str]], recall_indices: List[int]) -> int:
    prompt_tokens = _count_tokens(messages)

    if prompt_tokens <= MAX_PROMPT_TOKENS:
        return prompt_tokens

    # Drop recall messages first if needed
    for idx in reversed(recall_indices):
        if idx < len(messages):
            messages.pop(idx)

        prompt_tokens = _count_tokens(messages)
        if prompt_tokens <= MAX_PROMPT_TOKENS:
            return prompt_tokens

    while prompt_tokens > MAX_PROMPT_TOKENS and len(messages) > 1:
        messages.pop(1)
        prompt_tokens = _count_tokens(messages)

    if prompt_tokens > MAX_PROMPT_TOKENS:
        logger.warning(
            "Prompt still exceeds token budget",
            extra={
                "prompt_tokens": prompt_tokens,
                "budget": MAX_PROMPT_TOKENS,
            },
        )

    return prompt_tokens


def _format_recall_rows(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""

    lines: List[str] = []
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue

        direction = row.get("direction")
        speaker = "Customer" if direction == "inbound" else "Agent"
        created_at = row.get("created_at")
        timestamp = _format_timestamp(created_at)
        sanitized = text.replace("\n", " ")
        if len(sanitized) > 400:
            sanitized = sanitized[:397] + "..."
        lines.append(f"• [{timestamp}] {speaker}: {sanitized}")

    if not lines:
        return ""

    return "Relevant past messages:\n" + "\n".join(lines)


def _format_timestamp(value: Optional[str]) -> str:
    if not value:
        return "unknown"

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value[:16]
