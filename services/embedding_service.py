"""Embedding generation and retrieval helpers for chat messages."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import tiktoken
from openai import AsyncOpenAI

from config import get_settings
from services.supabase_client import get_supabase_client
from utils.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)
encoding = tiktoken.get_encoding("cl100k_base")


async def generate_message_embedding(message_id: str, text: Optional[str]) -> None:
    """Generate and persist an embedding for a chat message."""

    cleaned = (text or "").strip()
    if not cleaned:
        return

    chunk_payloads = _chunk_text(cleaned)
    if not chunk_payloads:
        return

    supabase = get_supabase_client()
    timestamp = datetime.now(timezone.utc).isoformat()

    rows: List[Dict[str, Any]] = []
    chunk_count = len(chunk_payloads)

    for chunk in chunk_payloads:
        chunk_text = chunk["text"]
        try:
            kwargs: Dict[str, Any] = {
                "model": settings.embeddings_model,
                "input": chunk_text,
            }
            if settings.embeddings_dimensions:
                kwargs["dimensions"] = settings.embeddings_dimensions
            response = await client.embeddings.create(**kwargs)
            vector = response.data[0].embedding if response.data else None
        except Exception as exc:  # pragma: no cover - external API failures
            logger.exception(
                "Failed to generate embedding chunk",
                extra={
                    "message_id": message_id,
                    "chunk_index": chunk["index"],
                    "chunk_length": len(chunk_text),
                },
            )
            return

        if not vector:
            return

        rows.append(
            {
                "message_id": message_id,
                "chunk_index": chunk["index"],
                "chunk_text": chunk_text,
                "start_token": chunk["start"],
                "end_token": chunk["end"],
                "chunk_count": chunk_count,
                "embedding": vector,
                "model": settings.embeddings_model,
                "created_at": timestamp,
            }
        )

    if not rows:
        return

    def _replace_rows() -> None:
        supabase.table("message_embeddings").delete().eq("message_id", message_id).execute()
        supabase.table("message_embeddings").upsert(rows).execute()

    await asyncio.to_thread(_replace_rows)

    if chunk_count > 1:
        logger.debug(
            "Stored chunked embeddings",
            extra={"message_id": message_id, "chunks": chunk_count},
        )


async def fetch_similar_messages(
    session_id: str,
    query_embedding: List[float],
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Return messages similar to the provided embedding using a Supabase RPC call."""

    supabase = get_supabase_client()

    def _query() -> List[Dict[str, Any]]:
        try:
            response = supabase.rpc(
                "match_session_messages",
                {
                    "session_id": session_id,
                    "query_embedding": query_embedding,
                    "match_limit": limit,
                },
            ).execute()
            return response.data or []
        except Exception as exc:  # pragma: no cover - RPC may not be defined yet
            logger.warning(
                "Embedding search RPC failed",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return []

    return await asyncio.to_thread(_query)


async def _fetch_chunk_rows(
    keys: List[Tuple[str, int]]
) -> Dict[Tuple[str, int], Dict[str, Any]]:
    """Fetch chunk metadata for specific message/chunk combinations."""

    if not keys:
        return {}

    message_ids = sorted({mid for mid, _ in keys})
    if not message_ids:
        return {}

    supabase = get_supabase_client()

    def _query() -> Dict[Tuple[str, int], Dict[str, Any]]:
        response = (
            supabase.table("message_embeddings")
            .select("message_id,chunk_index,chunk_text,start_token,end_token")
            .in_("message_id", message_ids)
            .execute()
        )
        rows = response.data or []
        result: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for row in rows:
            message_id = row.get("message_id")
            chunk_index = row.get("chunk_index")
            if isinstance(message_id, str) and isinstance(chunk_index, int):
                result[(message_id, chunk_index)] = row
        return result

    return await asyncio.to_thread(_query)


async def generate_query_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding vector for an arbitrary query string."""

    cleaned = text.strip()
    if not cleaned:
        return None

    try:
        kwargs: Dict[str, Any] = {
            "model": settings.embeddings_model,
            "input": cleaned,
        }
        if settings.embeddings_dimensions:
            kwargs["dimensions"] = settings.embeddings_dimensions
        response = await client.embeddings.create(**kwargs)
        vector = response.data[0].embedding if response.data else None
        return vector
    except Exception as exc:  # pragma: no cover - external API failures
        logger.exception("Failed to generate query embedding", exc_info=exc)
        return None


async def fetch_session_recall(
    session_id: str,
    query_text: str,
    *,
    limit: int,
    min_similarity: float,
) -> List[Dict[str, Any]]:
    """Return high-similarity prior messages for recall-aware prompts."""

    if not settings.enable_vector_recall:
        return []

    embedding = await generate_query_embedding(query_text)
    if not embedding:
        return []

    matches = await fetch_similar_messages(session_id, embedding, limit=limit)
    if not matches:
        return []

    filtered: List[Dict[str, Any]] = []
    missing_message_ids: List[str] = []

    for match in matches:
        similarity = match.get("similarity")
        if similarity is not None and similarity < min_similarity:
            continue

        message_id = match.get("message_id")
        if (not match.get("text") or not match.get("direction")) and isinstance(message_id, str):
            missing_message_ids.append(message_id)

        filtered.append(match)

    if not filtered:
        return []

    supplemental: Dict[str, Dict[str, Any]] = {}
    if missing_message_ids:
        supplemental = await _fetch_messages_by_ids(missing_message_ids)

    chunk_keys: List[Tuple[str, int]] = []
    for match in filtered:
        message_id = match.get("message_id")
        chunk_index = match.get("chunk_index")
        if (
            (not match.get("chunk_text") or not str(match.get("chunk_text")).strip())
            and isinstance(message_id, str)
            and isinstance(chunk_index, (int, float))
        ):
            chunk_keys.append((message_id, int(chunk_index)))

    chunk_details: Dict[Tuple[str, int], Dict[str, Any]] = {}
    if chunk_keys:
        chunk_details = await _fetch_chunk_rows(chunk_keys)

    recall_results: List[Dict[str, Any]] = []
    for match in filtered:
        message_id = match.get("message_id")
        if isinstance(message_id, str) and message_id in supplemental:
            base = supplemental[message_id]
            merged = {**match, **base}
        else:
            merged = match

        chunk_index_val = merged.get("chunk_index")
        chunk_text = (merged.get("chunk_text") or "").strip()
        if not chunk_text and isinstance(message_id, str) and isinstance(chunk_index_val, (int, float)):
            extra = chunk_details.get((message_id, int(chunk_index_val)))
            if extra:
                chunk_text = (extra.get("chunk_text") or "").strip()

        text = chunk_text or (merged.get("text") or "").strip()
        message_type = merged.get("message_type") or "text"

        if text:
            recall_results.append(merged)

    return recall_results


def _chunk_text(text: str) -> List[Dict[str, Any]]:
    """Split text into overlapping token chunks within embedding limits."""

    max_tokens = max(settings.embeddings_chunk_size_tokens, 0)
    overlap = max(settings.embeddings_chunk_overlap_tokens, 0)
    max_chunks = max(settings.embeddings_max_chunks, 1)

    tokens = encoding.encode(text)
    total_tokens = len(tokens)
    if max_tokens <= 0 or total_tokens <= max_tokens:
        return [
            {
                "index": 0,
                "text": text,
                "start": 0,
                "end": total_tokens,
            }
        ]

    overlap = min(overlap, max_tokens // 2)
    step = max(max_tokens - overlap, 1)

    chunks: List[Dict[str, Any]] = []
    for idx, start in enumerate(range(0, total_tokens, step)):
        end = start + max_tokens
        chunk_tokens = tokens[start:end]
        if not chunk_tokens:
            break
        chunks.append(
            {
                "index": idx,
                "text": encoding.decode(chunk_tokens),
                "start": start,
                "end": min(end, total_tokens),
            }
        )
        if len(chunks) >= max_chunks:
            break

    return chunks


def _average_embeddings(vectors: Iterable[List[float]]) -> List[float]:
    """Compute the element-wise average of embedding vectors."""

    vectors = list(vectors)
    if not vectors:
        return []

    length = len(vectors[0])
    aggregate = [0.0] * length

    for vec in vectors:
        for idx in range(length):
            aggregate[idx] += vec[idx]

    count = float(len(vectors))
    return [value / count for value in aggregate]


async def _fetch_messages_by_ids(message_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load minimal message fields required for recall snippets."""

    unique_ids = sorted({mid for mid in message_ids if isinstance(mid, str)})
    if not unique_ids:
        return {}

    supabase = get_supabase_client()

    def _query() -> Dict[str, Dict[str, Any]]:
        response = (
            supabase.table("chat_messages")
            .select("id,text,direction,created_at")
            .in_("id", unique_ids)
            .execute()
        )
        rows = response.data or []
        return {row["id"]: row for row in rows if isinstance(row, dict) and row.get("id")}

    return await asyncio.to_thread(_query)
