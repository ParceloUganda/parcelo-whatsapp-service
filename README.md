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

## Project Structure

- `app.py` – FastAPI entrypoint & router registration.
- `luminous_webhook.py` – webhook route, idempotency, Supabase persistence, agent trigger.
- `services/` – modular services for Supabase, Luminous, Telegram, and agent workflow.
- `utils/` – logging utilities.

## Next Steps

- Port full OpenAI agent from `parcelo_customer/lib/agents/parcelo-bot-workflow.ts` into `services/agent_runner.py`.
- Add automated tests and CI workflow.
- Deploy using Railway/Fly.io with `uvicorn app:app --host 0.0.0.0 --port $PORT`.
