"""Media download and processing helpers for WhatsApp attachments."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List

import httpx
from openai import AsyncOpenAI

from config import get_settings
from services.embedding_service import generate_message_embedding
from services.supabase_client import get_supabase_client
from utils.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


@dataclass(slots=True)
class MediaDownloadResult:
    message_id: str
    wa_media_id: str
    mime_type: str
    storage_path: str
    file_size: int
    checksum: Optional[str]
    downloaded_at: datetime


class MediaDownloadDisabled(Exception):
    """Raised when media download is disabled via configuration."""


def _ensure_enabled() -> None:
    if not settings.enable_media_download:
        raise MediaDownloadDisabled("Media download disabled via ENABLE_MEDIA_DOWNLOAD")


async def fetch_media_metadata(wa_media_id: str, *, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """Retrieve metadata for a WhatsApp media object."""

    _ensure_enabled()

    token = settings.luminous_api_key
    if not token:
        logger.warning("Missing luminous API token for media metadata fetch")
        return None

    url = f"https://graph.facebook.com/v19.0/{wa_media_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers)
    if response.status_code != 200:
        logger.warning(
            "Failed to fetch media metadata",
            extra={"wa_media_id": wa_media_id, "status": response.status_code},
        )
        return None

    data = response.json()
    download_url = data.get("url")
    mime_type = data.get("mime_type")
    if not download_url or not mime_type:
        logger.warning(
            "Incomplete media metadata",
            extra={"wa_media_id": wa_media_id},
        )
        return None

    return {"url": download_url, "mime_type": mime_type}


async def download_media_to_storage(
    *,
    message_id: str,
    wa_media_id: str,
    download_url: str,
    mime_type: str,
    timeout: float = 30.0,
) -> Optional[MediaDownloadResult]:
    """Download the media file and upload it to Supabase storage."""

    _ensure_enabled()

    bucket = settings.media_storage_bucket
    if not bucket:
        logger.warning("MEDIA_STORAGE_BUCKET not configured")
        return None

    token = settings.luminous_api_key
    if not token:
        logger.warning("Missing luminous API token for media download")
        return None

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(download_url, headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        logger.warning(
            "Media download failed",
            extra={"wa_media_id": wa_media_id, "status": response.status_code},
        )
        return None

    content = response.content
    if not content:
        logger.warning("Empty media content", extra={"wa_media_id": wa_media_id})
        return None

    file_size = len(content)
    checksum = hashlib.sha256(content).hexdigest()
    extension = _extension_for_mime(mime_type)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    storage_path = f"{message_id}/{wa_media_id}_{timestamp}{extension}"

    supabase = get_supabase_client()

    def _upload() -> None:
        supabase.storage.from_(bucket).upload(storage_path, content, {"content-type": mime_type})

    try:
        await asyncio.to_thread(_upload)
    except Exception as exc:  # pragma: no cover
        logger.exception(
            "Failed to upload media to storage",
            extra={"wa_media_id": wa_media_id, "bucket": bucket},
        )
        return None

    return MediaDownloadResult(
        message_id=message_id,
        wa_media_id=wa_media_id,
        mime_type=mime_type,
        storage_path=storage_path,
        file_size=file_size,
        checksum=checksum,
        downloaded_at=datetime.now(timezone.utc),
    )


async def record_chat_media(
    result: MediaDownloadResult,
    *,
    caption: Optional[str] = None,
    transcript: Optional[str] = None,
) -> None:
    """Persist metadata for the downloaded media and update chat message."""

    _ensure_enabled()

    supabase = get_supabase_client()

    expires_at = result.downloaded_at + timedelta(days=settings.media_retention_days)

    def _persist() -> None:
        payload = {
            "message_id": result.message_id,
            "wa_media_id": result.wa_media_id,
            "mime_type": result.mime_type,
            "storage_path": result.storage_path,
            "file_size": result.file_size,
            "checksum": result.checksum,
            "downloaded_at": result.downloaded_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if caption is not None:
            payload["caption"] = caption
        if transcript is not None:
            payload["transcript"] = transcript

        supabase.table("chat_media").upsert(payload).execute()
        supabase.table("chat_messages").update(
            {
                "media_url": result.storage_path,
                "media_mime_type": result.mime_type,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", result.message_id).execute()

    await asyncio.to_thread(_persist)


async def process_caption_if_needed(result: MediaDownloadResult) -> Optional[str]:
    if not settings.enable_vision_captions:
        return None
    if not result.mime_type.startswith("image/"):
        return None

    model = settings.vision_model
    if not model:
        logger.debug("Vision model not configured; skipping caption", extra={"message_id": result.message_id})
        return None

    signed_url = await _create_signed_url(result.storage_path)
    if not signed_url:
        logger.warning("Failed to create signed URL for captioning", extra={"message_id": result.message_id})
        return None

    prompt = "Describe this image for customer support context. Highlight objects, text, and any notable scene details."

    try:
        response = await openai_client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": signed_url, "detail": "low"},
                    ],
                }
            ],
        )
    except Exception as exc:  # pragma: no cover - external service
        logger.exception("Vision captioning failed", extra={"message_id": result.message_id})
        return None

    caption = (response.output_text or "").strip()
    if not caption:
        logger.debug("Vision model returned empty caption", extra={"message_id": result.message_id})
        return None

    await record_chat_media(result, caption=caption)
    return caption


async def process_transcription_if_needed(result: MediaDownloadResult) -> Optional[str]:
    if not settings.enable_audio_transcription:
        return None
    if not result.mime_type.startswith("audio/"):
        return None

    model = settings.transcription_model
    if not model:
        logger.debug("Transcription model not configured; skipping", extra={"message_id": result.message_id})
        return None

    if result.file_size and result.file_size > 25 * 1024 * 1024:
        logger.warning("Audio file too large for transcription", extra={"message_id": result.message_id, "size": result.file_size})
        return None

    supabase = get_supabase_client()
    bucket = settings.media_storage_bucket

    def _download() -> bytes:
        response = supabase.storage.from_(bucket).download(result.storage_path)
        return response

    try:
        audio_bytes = await asyncio.to_thread(_download)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to download media for transcription", extra={"message_id": result.message_id})
        return None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=_extension_for_mime(result.mime_type) or ".audio") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            transcript_response = await openai_client.audio.transcriptions.create(
                model=model,
                file=audio_file,
            )
    except Exception:  # pragma: no cover
        logger.exception("Audio transcription failed", extra={"message_id": result.message_id})
        return None
    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                logger.warning("Failed to remove temp file", extra={"path": tmp_path})

    transcript_text = (transcript_response.text or "").strip()
    if not transcript_text:
        logger.debug("Transcription returned empty text", extra={"message_id": result.message_id})
        return None

    await record_chat_media(result, transcript=transcript_text)
    await generate_message_embedding(result.message_id, transcript_text)
    return transcript_text


def _extension_for_mime(mime_type: str) -> str:
    ext = mimetypes.guess_extension(mime_type)
    return ext or ""


async def _create_signed_url(path: str) -> Optional[str]:
    supabase = get_supabase_client()

    def _sign() -> Optional[str]:
        try:
            response = supabase.storage.from_(settings.media_storage_bucket).create_signed_url(path, 300)
            return response.get("signedURL") or response.get("signed_url")
        except Exception:
            return None

    return await asyncio.to_thread(_sign)


async def cleanup_expired_media_batch(limit: int = 50) -> Dict[str, int]:
    """Delete expired media records and storage objects."""

    _ensure_enabled()

    supabase = get_supabase_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _fetch() -> List[Dict[str, Any]]:
        response = (
            supabase.table("chat_media")
            .select("id,message_id,storage_path,wa_media_id")
            .lte("expires_at", now_iso)
            .limit(limit)
            .execute()
        )
        return response.data or []

    expired = await asyncio.to_thread(_fetch)
    if not expired:
        return {"deleted": 0, "failed": 0}

    deleted = 0
    failed = 0

    for record in expired:
        try:
            await _delete_media_entry(record)
            deleted += 1
        except Exception:  # pragma: no cover - defensive
            failed += 1
            logger.exception(
                "Failed to delete media entry",
                extra={"media_id": record.get("id"), "wa_media_id": record.get("wa_media_id")},
            )

    logger.info(
        "Media cleanup batch complete",
        extra={"attempted": len(expired), "deleted": deleted, "failed": failed},
    )

    return {"deleted": deleted, "failed": failed}


async def purge_session_media(session_id: str) -> Dict[str, int]:
    """Manually purge all media associated with a chat session."""

    _ensure_enabled()

    supabase = get_supabase_client()

    def _fetch() -> List[Dict[str, Any]]:
        response = (
            supabase.table("chat_media")
            .select("id,message_id,storage_path,wa_media_id")
            .in_("message_id", (
                supabase.table("chat_messages")
                .select("id")
                .eq("session_id", session_id)
                .execute()
                .data or []
            ))
        )
        rows = response.data or []
        return rows

    records = await asyncio.to_thread(_fetch)
    deleted = 0
    failed = 0

    for record in records:
        try:
            await _delete_media_entry(record)
            deleted += 1
        except Exception:  # pragma: no cover
            failed += 1
            logger.exception(
                "Failed to purge session media",
                extra={"session_id": session_id, "media_id": record.get("id")},
            )

    return {"deleted": deleted, "failed": failed}


async def _delete_media_entry(record: Dict[str, Any]) -> None:
    supabase = get_supabase_client()
    bucket = settings.media_storage_bucket
    storage_path = record.get("storage_path")
    message_id = record.get("message_id")
    media_id = record.get("id")

    def _remove_storage() -> None:
        if storage_path:
            supabase.storage.from_(bucket).remove([storage_path])

    def _delete_row() -> None:
        supabase.table("chat_media").delete().eq("id", media_id).execute()
        if message_id:
            supabase.table("chat_messages").update(
                {
                    "media_url": None,
                    "media_mime_type": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", message_id).execute()

    await asyncio.to_thread(_remove_storage)
    await asyncio.to_thread(_delete_row)
