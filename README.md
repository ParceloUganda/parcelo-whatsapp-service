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
