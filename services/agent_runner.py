"""Simple OpenAI-powered agent workflow."""

from typing import Any, Dict

from openai import AsyncOpenAI

from config import get_settings
from utils.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


async def run_agent_workflow(
    *,
    message_text: str,
    customer_id: str,
    session_id: str,
    phone_number: str,
    customer_name: str | None = None,
) -> Dict[str, Any]:
    """Run a lightweight conversational agent using OpenAI chat completions."""

    system_prompt = (
        "You are ParceloBot, a helpful WhatsApp assistant for Parcelo Uganda. "
        "Provide concise, friendly answers. Offer to help with price quotes, order tracking, payments, "
        "and general questions. Keep tone warm and professional."
    )

    user_context = (
        f"Customer: {customer_name or 'Customer'}\n"
        f"Phone: {phone_number}\n"
        f"Message: {message_text}"
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_context},
            ],
            temperature=0.6,
            max_tokens=400,
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
            "model": "gpt-4o-mini",
            "customer_id": customer_id,
            "session_id": session_id,
        },
    }
