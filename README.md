# Parcelo WhatsApp Service (Python)

## Quick Start

1. Create a virtual environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
2. Copy `.env.sample` to `.env` and fill in real credentials.
3. Run the API locally:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
4. Expose via ngrok (optional) and point Luminous webhook to `https://<ngrok>/api/luminous/webhook`.

## Environment Variables

- `ENVIRONMENT`, `LOG_LEVEL` – runtime configuration.
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` – database access.
- `OPENAI_API_KEY` – agent workflow.
- `LUMINOUS_API_URL`, `LUMINOUS_API_KEY` – outbound WhatsApp messages.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_NOTIFICATIONS_ENABLED` – optional alerts.

## Phase 5 — Media Handling Overview

- **[Pipeline]** When WhatsApp delivers an image, audio clip, or document, `luminous_webhook.handle_message_received()` queues `services/media_service.process_media_message()`. The service fetches metadata from the WhatsApp API, streams the file into the private `chat-media` bucket, and records a row in `public.chat_media` linked to the originating `chat_messages.id`.
- **[Optional enrichment]** If `ENABLE_VISION_CAPTIONS=true` and a `VISION_MODEL` (e.g., `gpt-4.1-mini`) is set, `process_caption_if_needed()` generates a short caption via OpenAI Responses and stores it in `chat_media.caption`, then calls `generate_message_embedding()` so the caption participates in recall. Similarly, when `ENABLE_AUDIO_TRANSCRIPTION=true` and `TRANSCRIPTION_MODEL` is configured, `process_transcription_if_needed()` transcribes audio (<=25 MB) and stores text in `chat_media.transcript` for embeddings.
- **[Configuration]** Tunable environment variables (`config.py`, `.env.sample`): `ENABLE_MEDIA_DOWNLOAD`, `MEDIA_STORAGE_BUCKET`, `MEDIA_RETENTION_DAYS`, `MEDIA_CLEANUP_INTERVAL_MINUTES`, `ENABLE_VISION_CAPTIONS`, `VISION_MODEL`, `ENABLE_AUDIO_TRANSCRIPTION`, `TRANSCRIPTION_MODEL`. Disable enrichment by leaving toggles `false` or omitting model names.
- **[Cleanup]** `workers/media_cleanup_worker.py` runs on startup (`app.py`) and calls `cleanup_expired_media_batch()` hourly by default, deleting storage objects and rows whose `expires_at` has passed. Use `run_single_cleanup()` or `purge_session_media()` for manual purges.
- **[Runbook]** Watch application logs for entries such as `Media download failed`, `Vision captioning failed`, `Audio transcription failed`, and `Media cleanup iteration`. Investigate repeated failures (token issues, storage permissions, model access) and adjust env vars as needed. Ensure observability captures these logs so on-call staff can respond quickly.

## Phase 4 — Deep Recall Overview

- **[Pipeline]** Inbound and outbound chat messages are persisted via `services/chat_service.py`. Background tasks in `luminous_webhook.py` call `services/embedding_service.generate_message_embedding()` to slice long texts into ~700-token chunks (140-token overlap) and store each segment in `public.message_embeddings`.
- **[Schema]** `public.message_embeddings` now holds one row per chunk with columns `message_id`, `chunk_index`, `chunk_text`, `start_token`, `end_token`, `embedding`, `chunk_count`, `model`, `created_at`. Primary key is `(message_id, chunk_index)`.
- **[Retrieval]** `services/embedding_service.fetch_session_recall()` embeds the user’s latest prompt, calls the `public.match_session_messages` RPC, and enriches results with chunk metadata. `services/agent_runner.build_prompt_messages()` injects formatted recall snippets ahead of the sliding window, trimming recall entries first when tokens overflow.
- **[Configuration]** Tunable knobs in `config.py` / `.env.sample`: `EMBEDDINGS_MODEL`, `EMBEDDINGS_DIMENSIONS`, `EMBEDDINGS_CHUNK_SIZE_TOKENS`, `EMBEDDINGS_CHUNK_OVERLAP_TOKENS`, `EMBEDDINGS_MAX_CHUNKS`, `EMBEDDINGS_RECALL_LIMIT`, `EMBEDDINGS_MIN_SIMILARITY`, `ENABLE_VECTOR_RECALL`. Adjust to balance recall depth vs. cost.
- **[Operations]** Monitor `chunk_count` logs, Supabase rows, and agent metadata fields `recall_included` / `recall_count`. Disable recall quickly by setting `ENABLE_VECTOR_RECALL=false` or `EMBEDDINGS_RECALL_LIMIT=0` if API usage spikes.
- **[Costs & Safety]** Chunking reduces token waste for long histories, while per-chunk storage keeps similar topics distinct. Average OpenAI embedding pricing applies per chunk; set conservative chunk size/overlap in production and review Supabase retention policies regularly.

## WhatsApp Compliance & Privacy

- **24-hour service window**
  Ensure outbound replies occur within 24 hours of the customer’s last message unless using a Meta-approved template. Reference: [Meta Messaging Policy](https://business.whatsapp.com/policies)
- **Customer consent management**
  Collect explicit opt-in before messaging. Provide easy opt-out (e.g., STOP) and record consent state in storage. Reference: [WhatsApp Opt-in Guidelines](https://developers.facebook.com/docs/whatsapp/overview#user-opt-in)
- **Data retention**
  Limit stored chat data to the minimum needed (default: retain transcripts 30 days, summaries longer if required). Purge or anonymize on request to comply with regulations (GDPR, etc.). Reference: [WhatsApp Business Terms](https://business.whatsapp.com/terms-and-policies)
- **Privacy contact**
  Publish a privacy policy and support channel for data inquiries (e.g., privacy@parcelo.com). Document handling of local storage requirements for regulated sectors. Reference: [Meta Local Storage Overview](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/local-storage)

## Project Structure

- `app.py` – FastAPI entrypoint & router registration.
- `luminous_webhook.py` – webhook route, idempotency, Supabase persistence, agent trigger.
- `services/` – modular services for Supabase, Luminous, Telegram, and agent workflow.
- `utils/` – logging utilities.

## Next Steps

- Port full OpenAI agent from `parcelo_customer/lib/agents/parcelo-bot-workflow.ts` into `services/agent_runner.py`.
- Add automated tests and CI workflow.
- Deploy using Railway/Fly.io with `uvicorn app:app --host 0.0.0.0 --port $PORT`.

## Deploying on Northflank

1. **Prepare repository**
   - Ensure the new `Dockerfile` is committed at repo root.
   - Keep secrets out of git (`.env`, API keys) and store values in Northflank secrets.
2. **Create project services**
   - Add a *Build service* linked to your GitHub repo and branch (`main`). Northflank will use the Dockerfile to build the image.
   - Add a *Deployment service* consuming the build output. Choose plan size (e.g., `nf-compute-100-1` to start) and set replicas.
3. **Configure runtime**
   - Expose port **8080** (matches `Dockerfile` `EXPOSE`).
   - Add environment variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `LUMINOUS_API_KEY`, `TELEGRAM_BOT_TOKEN`, etc.) via Northflank secrets.
4. **Set up pipeline (optional)**
   - Create a Pipeline that triggers the build service on push, then deploys automatically.
   - Enable preview environments for PR testing if needed.
5. **DNS and health checks**
   - Use the generated Northflank URL or map a custom domain. Configure `/healthz` as the readiness probe for uptime monitoring.
