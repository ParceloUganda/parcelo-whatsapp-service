"""Task-specific multi-agent orchestration for Parcelo WhatsApp assistant."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
import tiktoken
from agents import (
    Agent,
    ModelSettings,
    Runner,
    RunConfig,
    TResponseInputItem,
    function_tool,
    set_default_openai_key,
)
from openai import AsyncOpenAI
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel, Field

from config import get_settings
from services.embedding_service import fetch_session_recall
from services.supabase_client import get_supabase_client
from utils.logging import get_logger


settings = get_settings()
logger = get_logger(__name__)

# Create OpenAI client with HTTP/1.1 to avoid HTTP/2 streaming issues
client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    http_client=httpx.AsyncClient(http2=False)
)
encoding = tiktoken.get_encoding("cl100k_base")

set_default_openai_key(settings.openai_api_key)

WINDOW_SIZE = max(settings.llm_window_size, 1)
MAX_PROMPT_TOKENS = max(settings.llm_max_prompt_tokens, 1024)


class AgentRoute(str, Enum):
    QUOTATION = "quotation"
    WISHLIST = "wishlist"
    PAYMENTS = "payments"
    ORDERS = "orders"
    ESCALATION = "escalation"
    SHIPPING = "shipping"
    SUBSCRIPTION = "subscription"
    WEB_ACCESS = "web_access"
    GENERAL = "general"
    UNSAFE = "unsafe"


class ClassifierOutput(BaseModel):
    route: AgentRoute = Field(description="Selected downstream agent")
    reasoning: Optional[str] = Field(default=None, description="Brief rationale for routing decision")


class QuotationOutput(BaseModel):
    tool: str = Field(description="Tool to invoke, e.g. CreateQuotation or GetQuotation")
    action: str = Field(description="Action or sub-command for the tool")
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str = Field(description="Customer-facing reply")


class WishlistOutput(BaseModel):
    tool: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str


class PaymentsOutput(BaseModel):
    tool: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str


class OrdersOutput(BaseModel):
    tool: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str


class EscalationOutput(BaseModel):
    escalate: bool
    tool: Optional[str] = Field(default=None, description="Tool used to escalate, if any")
    reason: str
    category: str = Field(description="Escalation category: payment_issue, delivery_problem, product_inquiry, complaint, technical_issue, refund_request, other")
    sentiment: str = Field(description="Detected customer sentiment: positive, neutral, negative, angry, confused")
    priority: str = Field(description="Ticket priority: low, medium, high, urgent")
    journey_stage: Optional[str] = Field(default=None, description="Customer journey stage: quotation, cart, payment, delivery")
    response_text: str


class ShippingOutput(BaseModel):
    tool: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str


class SubscriptionOutput(BaseModel):
    tool: str = Field(description="Tool to invoke, e.g. UpgradeSubscription")
    action: str = Field(description="Action like 'upgrade', 'check_status'")
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str = Field(description="Customer-facing reply")
    payment_link: Optional[str] = Field(default=None, description="Pesapal payment link if applicable")


class WebAccessOutput(BaseModel):
    tool: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str
    magic_link: Optional[str] = Field(default=None, description="Magic link URL for website access")


class FeedbackOutput(BaseModel):
    tool: str = Field(description="Tool to invoke for feedback")
    action: str = Field(description="Feedback action")
    feedback_type: str = Field(description="Type: general, order_experience, delivery_experience, product_quality, customer_service, app_usability, suggestion, complaint")
    sentiment: str = Field(description="Detected sentiment: positive, neutral, negative")
    rating: Optional[int] = Field(default=None, description="Rating 1-5 stars if provided")
    requires_follow_up: bool = Field(default=False, description="Whether feedback needs management response")
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_text: str

BASE_SYSTEM_PROMPT = (
    "You are ParceloBot, a helpful WhatsApp assistant for Parcelo Uganda. "
    "Provide concise, friendly answers. Offer to help with price quotes, order tracking, payments, "
    "and general questions. Keep tone warm and professional. Please don't repeat the person's names and number or what you do. "
    "Avoid informal language or tone. You have a professional yet friendly personality. "
    "Avoid any mention of AI agent being used at Parcelo."
)


def _tool(name: str, description: str):
    return function_tool(
        name_override=name,
        description_override=description,
        strict_mode=False,
    )


def _build_agent(
    *,
    name: str,
    instructions: str,
    model: str,
    output_type: Optional[type[BaseModel]] = None,
    reasoning_effort: Optional[str] = None,
    tools: Optional[List[Any]] = None,
) -> Agent:
    settings_kwargs = {
        "store": True,
    }
    if reasoning_effort:
        settings_kwargs["reasoning"] = Reasoning(effort=reasoning_effort)

    return Agent(
        name=name,
        instructions=instructions,
        model=model,
        output_type=output_type,
        model_settings=ModelSettings(**settings_kwargs),
        tools=list(tools) if tools else [],
    )


@_tool("CreateQuotation", "Create a new parcel quotation")
def create_quotation_tool(
    customer_id: str,
    items: List[Dict[str, Any]],
    notes: Optional[str] = None,
) -> str:
    payload = {"customer_id": customer_id, "items": items, "notes": notes}
    logger.info("CreateQuotation tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("GetQuotation", "Retrieve quotation details")
def get_quotation_tool(quote_id: Optional[str] = None, quote_link: Optional[str] = None) -> str:
    payload = {"quote_id": quote_id, "quote_link": quote_link}
    logger.info("GetQuotation tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("WishlistCRUD", "Manage wishlist items")
def wishlist_crud_tool(
    customer_id: str,
    action: str,
    item: Optional[Dict[str, Any]] = None,
) -> str:
    payload = {"customer_id": customer_id, "action": action, "item": item}
    logger.info("WishlistCRUD tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("MoveWishlistToCart", "Move wishlist items to cart")
def move_wishlist_to_cart_tool(
    customer_id: str,
    wishlist_item_ids: List[str],
) -> str:
    payload = {"customer_id": customer_id, "wishlist_item_ids": wishlist_item_ids}
    logger.info("MoveWishlistToCart tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("CartCRUD", "Manage cart items")
def cart_crud_tool(
    customer_id: str,
    action: str,
    item: Optional[Dict[str, Any]] = None,
) -> str:
    payload = {"customer_id": customer_id, "action": action, "item": item}
    logger.info("CartCRUD tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("MoveCartToWishlist", "Move cart item to wishlist")
def move_cart_to_wishlist_tool(
    customer_id: str,
    cart_item_id: str,
    wishlist_id: Optional[str] = None,
) -> str:
    """
    Move item from cart to wishlist via /api/cart/item/move-to-wishlist
    """
    payload = {
        "customer_id": customer_id,
        "cart_item_id": cart_item_id,
        "wishlist_id": wishlist_id,
    }
    logger.info("MoveCartToWishlist tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("CreateOrderFromCart", "Create order from cart items")
def create_order_from_cart_tool(
    customer_id: str,
    cart_id: str,
    shipping_address: Dict[str, Any],
    payment_method: str,
) -> str:
    """
    Create order from cart via /api/s2s/orders
    """
    payload = {
        "customer_id": customer_id,
        "cart_id": cart_id,
        "shipping_address": shipping_address,
        "payment_method": payment_method,
    }
    logger.info("CreateOrderFromCart tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("CreatePaymentIntent", "Create a payment intent")
def create_payment_intent_tool(
    order_or_quote_id: str,
    amount: float,
    currency: str,
    method: str,
) -> str:
    payload = {
        "order_or_quote_id": order_or_quote_id,
        "amount": amount,
        "currency": currency,
        "method": method,
    }
    logger.info("CreatePaymentIntent tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("GetPaymentStatus", "Check payment status")
def get_payment_status_tool(payment_id: str) -> str:
    payload = {"payment_id": payment_id}
    logger.info("GetPaymentStatus tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("CreateTicket", "Open a support ticket")
def create_ticket_tool(
    customer_id: str,
    topic: str,
    message: str,
    files: Optional[List[str]] = None,
) -> str:
    payload = {
        "customer_id": customer_id,
        "topic": topic,
        "message": message,
        "files": files,
    }
    logger.info("CreateTicket tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("ReplyTicket", "Reply to a support ticket")
def reply_ticket_tool(
    ticket_id: str,
    message: str,
    files: Optional[List[str]] = None,
) -> str:
    payload = {"ticket_id": ticket_id, "message": message, "files": files}
    logger.info("ReplyTicket tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("EscalateToHuman", "Escalate conversation to human agent")
def escalate_to_human_tool(
    customer_id: str,
    reason: str,
    category: str,
    sentiment: str,
    priority: str,
    journey_stage: Optional[str] = None,
) -> str:
    """
    Escalate conversation to human support agent.
    
    Args:
        customer_id: Customer UUID
        reason: Why escalation is needed (full explanation)
        category: payment_issue, delivery_problem, product_inquiry, complaint, 
                 technical_issue, refund_request, other
        sentiment: positive, neutral, negative, angry, confused
        priority: low, medium, high, urgent
        journey_stage: quotation, cart, payment, delivery (optional)
    """
    payload = {
        "customer_id": customer_id,
        "reason": reason,
        "category": category,
        "sentiment": sentiment,
        "priority": priority,
        "journey_stage": journey_stage,
    }
    logger.info("EscalateToHuman tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "action": "escalate", "payload": payload})


@_tool("TrackShipment", "Track shipment status")
def track_shipment_tool(
    parcel_id: Optional[str] = None,
    order_id: Optional[str] = None,
) -> str:
    payload = {"parcel_id": parcel_id, "order_id": order_id}
    logger.info("TrackShipment tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("UpgradeSubscription", "Upgrade customer subscription plan")
def upgrade_subscription_tool(
    customer_id: str,
    plan_code: str,  # 'standard' or 'parcelo_plus'
    billing: str,    # 'monthly' or 'yearly'
    payment_method: str,  # 'momo' or 'pesapal'
    phone: Optional[str] = None,  # Required for MoMo
    email: Optional[str] = None,  # Required for Pesapal
) -> str:
    """
    Create subscription checkout via /api/subscription/checkout
    """
    payload = {
        "customer_id": customer_id,
        "plan_code": plan_code,
        "billing": billing,
        "payment_method": payment_method,
        "phone": phone,
        "email": email,
    }
    logger.info("UpgradeSubscription tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("GetSubscriptionStatus", "Check current subscription details")
def get_subscription_status_tool(customer_id: str) -> str:
    """
    Get subscription summary via /api/subscription/summary
    """
    payload = {"customer_id": customer_id}
    logger.info("GetSubscriptionStatus tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("CheckPaymentStatus", "Check payment status for subscription or order")
def check_payment_status_tool(
    reference_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    tracking_id: Optional[str] = None,
) -> str:
    """
    Poll payment status via /api/subscription/payment-callback
    """
    payload = {
        "reference_id": reference_id,
        "subscription_id": subscription_id,
        "tracking_id": tracking_id,
    }
    logger.info("CheckPaymentStatus tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("GetSubscriptionPlans", "Get current subscription plans with prices and features")
def get_subscription_plans_tool() -> str:
    """
    Returns the current subscription plans from Next.js config.
    Plans, prices, and features can change, so always fetch fresh data.
    """
    logger.info("GetSubscriptionPlans tool invoked")
    return json.dumps({"status": "pending", "action": "fetch_subscription_plans"})


@_tool("GetPaymentMethods", "Check which payment methods are currently available")
def get_payment_methods_tool() -> str:
    """
    Returns the currently enabled payment methods (MoMo/Pesapal).
    Always call this before offering payment options to users.
    """
    logger.info("GetPaymentMethods tool invoked")
    return json.dumps({"status": "pending", "action": "fetch_payment_methods"})


@_tool("RequestWebsiteAccess", "Send magic link for user to access orders on website")
def request_website_access_tool(
    customer_id: str,
    phone_number: str,
) -> str:
    """
    Generates a magic link that allows WhatsApp user to access their orders
    on the Parcelo website.
    
    Args:
        customer_id: The customer's UUID from the database
        phone_number: Customer's phone number (e.g., '256700123456')
    
    Returns:
        JSON string with magic link or error
    """
    payload = {
        "customer_id": customer_id,
        "phone_number": phone_number,
    }
    logger.info("RequestWebsiteAccess tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "payload": payload})


@_tool("CollectFeedback", "Collect customer feedback, ratings, or suggestions")
def collect_feedback_tool(
    customer_id: str,
    feedback_type: str,
    feedback_text: str,
    sentiment: str,
    rating: Optional[int] = None,
    order_id: Optional[str] = None,
    journey_stage: Optional[str] = None,
    requires_follow_up: bool = False,
) -> str:
    """
    Collect customer feedback, ratings, suggestions, or opinions.
    
    Args:
        customer_id: Customer UUID
        feedback_type: general, order_experience, delivery_experience, product_quality,
                      customer_service, app_usability, suggestion, complaint
        feedback_text: The actual feedback text from customer
        sentiment: positive, neutral, negative
        rating: Optional 1-5 star rating
        order_id: Optional order reference
        journey_stage: quotation, cart, payment, delivery, post_delivery
        requires_follow_up: Whether management should review this
    """
    payload = {
        "customer_id": customer_id,
        "feedback_type": feedback_type,
        "feedback_text": feedback_text,
        "sentiment": sentiment,
        "rating": rating,
        "order_id": order_id,
        "journey_stage": journey_stage,
        "requires_follow_up": requires_follow_up,
    }
    logger.info("CollectFeedback tool invoked", extra={"payload": payload})
    return json.dumps({"status": "pending", "action": "collect_feedback", "payload": payload})


async def generate_magic_link_for_customer(
    customer_id: str,
    phone_number: str,
) -> Dict[str, Any]:
    """
    Call Next.js API to generate magic link.
    
    Returns:
        {
            "success": True,
            "magic_link": "https://parceloug.com/auth/magic?token=...",
            "expires_at": "2025-10-15T14:00:00Z"
        }
    """
    if not settings.service_secret:
        logger.error("SERVICE_SECRET not configured")
        return {
            "success": False,
            "error": "Service configuration error"
        }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.nextjs_api_url}/api/auth/generate-magic-link",
                json={
                    "phone_number": phone_number,
                    "customer_id": customer_id,
                },
                headers={
                    "X-Service-Token": settings.service_secret,
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "Magic link generated successfully",
                    extra={"customer_id": customer_id, "phone_number": phone_number}
                )
                return data
            else:
                logger.error(
                    f"Failed to generate magic link: {response.status_code}",
                    extra={"response": response.text}
                )
                return {
                    "success": False,
                    "error": "Failed to generate access link"
                }
                
    except Exception as e:
        logger.error(f"Magic link generation error: {e}")
        return {
            "success": False,
            "error": "Service temporarily unavailable"
        }


async def get_subscription_plans() -> Dict[str, Any]:
    """
    Get current subscription plans from Next.js.
    
    Returns:
        {
            "plans": [...],
            "count": 3,
            "currency": "UGX"
        }
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.nextjs_api_url}/api/subscription/plans",
                timeout=5.0
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Subscription plans fetched: {data.get('count', 0)} plans")
                return data
            else:
                logger.error(f"Failed to fetch plans: {response.status_code}")
                return {"plans": [], "error": "Unable to fetch plans"}
                
    except Exception as e:
        logger.error(f"Subscription plans fetch error: {e}")
        return {"plans": [], "error": "Service temporarily unavailable"}


async def get_available_payment_methods() -> Dict[str, Any]:
    """
    Get currently enabled payment methods from Next.js.
    
    Returns:
        {
            "available_methods": [...],
            "config": {
                "momo_enabled": false,
                "pesapal_enabled": true
            }
        }
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.nextjs_api_url}/api/payment-methods",
                timeout=5.0
            )
            
            if response.status_code == 200:
                data = response.json()
                methods = data.get("available_methods", [])
                logger.info(
                    f"Payment methods fetched: {len(methods)} available",
                    extra={"methods": [m["id"] for m in methods]}
                )
                return data
            else:
                logger.error(f"Failed to fetch payment methods: {response.status_code}")
                return {
                    "available_methods": [],
                    "config": {"momo_enabled": False, "pesapal_enabled": True}
                }
                
    except Exception as e:
        logger.error(f"Payment methods fetch error: {e}")
        return {
            "available_methods": [],
            "config": {"momo_enabled": False, "pesapal_enabled": True}
        }


classifier_agent = _build_agent(
    name="Classifier Agent",
    instructions=(
        "Read the most recent customer message and classify the intent. "
        "Return one of: quotation, wishlist, payments, orders, escalation, shipping, subscription, web_access, general, unsafe. "
        "\n\n"
        "Use 'web_access' when user wants to: "
        "- See orders on website "
        "- View account on browser "
        "- Access full account details "
        "- Log into website "
        "- Check orders online "
        "\n\n"
        "Use 'subscription' for: plan upgrades, subscription status, plan comparisons, billing changes. "
        "Use 'payments' for: order payments, payment status for completed orders. "
        "Use 'quotation' for: price quotes, getting quotations. "
        "Use 'wishlist' for: saving items, moving items between wishlist and cart. "
        "\n\n"
        "Classify as unsafe if the user asks for disallowed content or the request must be escalated."
    ),
    model="gpt-5-nano",
    output_type=ClassifierOutput,
    reasoning_effort="low",
)

quotation_agent = _build_agent(
    name="Quotation Agent",
    instructions=(
        "Assist with Parcelo quotation workflows. Determine if the customer wants a new quote or information about an existing quote. "
        "Use the provided tools abstractly (CreateQuotation, GetQuotation) and prepare a response summarizing next steps. "
        "Collect pickup, drop-off, parcel details, and service level when needed."
    ),
    model="gpt-5-nano",
    output_type=QuotationOutput,
    reasoning_effort="low",
    tools=[create_quotation_tool, get_quotation_tool],
)


wishlist_agent = _build_agent(
    name="Wishlist & Cart Agent",
    instructions=(
        "Handle wishlist and cart management. Determine if the user wants to add/remove/list wishlist items, move to cart, or modify cart items. "
        "Map the intent to actions for WishlistCRUD, MoveWishlistToCart, MoveCartToWishlist, or CartCRUD tools. "
        "Always respond with a clear confirmation and next steps."
    ),
    model="gpt-5-nano",
    output_type=WishlistOutput,
    reasoning_effort="low",
    tools=[wishlist_crud_tool, move_wishlist_to_cart_tool, move_cart_to_wishlist_tool, cart_crud_tool],
)

payments_agent = _build_agent(
    name="Payments Agent",
    instructions=(
        "Help customers initiate or check payments. Determine whether to create a payment intent or fetch payment status via available tools. "
        "Gather payment amount, method, and order details when necessary."
    ),
    model="gpt-5-nano",
    output_type=PaymentsOutput,
    reasoning_effort="low",
    tools=[create_payment_intent_tool, get_payment_status_tool],
)

orders_agent = _build_agent(
    name="Orders & Support Agent",
    instructions=(
        "Support order-related questions and basic support. Open or reply to support tickets or answer simple order status questions. "
        "Also handle creating orders from cart when customer is ready to checkout. "
        "Decide between CreateTicket, ReplyTicket, CreateOrderFromCart, or providing informational answers."
    ),
    model="gpt-5-nano",
    output_type=OrdersOutput,
    reasoning_effort="low",
    tools=[create_ticket_tool, reply_ticket_tool, create_order_from_cart_tool],
)

escalation_agent = _build_agent(
    name="Escalation Agent",
    instructions=(
        "Determine whether the conversation should be escalated to a human support agent. "
        "\n\n"
        "**Escalate when:**\n"
        "- Customer is frustrated, angry, or upset\n"
        "- Issue requires manual intervention (refunds, damaged items, complex problems)\n"
        "- Customer explicitly asks for human agent or manager\n"
        "- Bot cannot resolve the issue after 2-3 attempts\n"
        "- Payment disputes or billing issues\n"
        "- Delivery problems (lost package, damaged goods)\n"
        "- Complaints about service quality\n"
        "\n\n"
        "**Detect customer sentiment carefully:**\n"
        "- angry: Customer uses harsh language, demands refund, threatens to leave\n"
        "- negative: Customer disappointed but not hostile\n"
        "- confused: Customer doesn't understand process\n"
        "- neutral: Matter-of-fact issue reporting\n"
        "- positive: Polite even when having issue\n"
        "\n\n"
        "**Set priority based on:**\n"
        "- urgent: Angry customer, time-sensitive issue, high-value order\n"
        "- high: Frustrated customer, payment problem, delivery delay\n"
        "- medium: General inquiries, minor issues\n"
        "- low: Simple questions, positive feedback\n"
        "\n\n"
        "**Categories:**\n"
        "- payment_issue: Payment failed, not processed, wrong amount\n"
        "- delivery_problem: Package lost, delayed, damaged\n"
        "- product_inquiry: Questions about product, availability\n"
        "- complaint: Service complaint, dissatisfaction\n"
        "- technical_issue: App/website problems\n"
        "- refund_request: Customer wants money back\n"
        "- other: Doesn't fit other categories\n"
        "\n\n"
        "Always provide clear reason for escalation and accurate sentiment detection."
    ),
    model="gpt-5-nano",
    output_type=EscalationOutput,
    reasoning_effort="low",
    tools=[escalate_to_human_tool],
)

shipping_agent = _build_agent(
    name="Shipping Agent",
    instructions=(
        "Provide shipment tracking assistance. Use the TrackShipment tool conceptually to fetch status and explain it clearly. "
        "Ask for tracking numbers if missing."
    ),
    model="gpt-5-nano",
    output_type=ShippingOutput,
    reasoning_effort="low",
    tools=[track_shipment_tool],
)

subscription_agent = _build_agent(
    name="Subscription Agent",
    instructions=(
        "Handle subscription upgrades for Parcelo. "
        "\n\n"
        "**CRITICAL: Plans and prices change - ALWAYS fetch current data first!** "
        "1. Call GetSubscriptionPlans to get latest plan details (prices, features, quotas) "
        "2. Call GetPaymentMethods to see which payment options are enabled "
        "\n\n"
        "**DO NOT use hardcoded plan information.** "
        "**DO NOT assume prices or features.** "
        "**ALWAYS get fresh data from the tools.** "
        "\n\n"
        "After fetching current plans, present them to the user with: "
        "- Plan name and monthly price "
        "- Key features (requests/month, service fee, minimum spend) "
        "- Available payment methods "
        "\n\n"
        "Payment flow: "
        "- MTN MoMo: User gets prompt on phone (stays in WhatsApp) "
        "- Pesapal: User clicks link to pay (opens browser) "
        "\n\n"
        "For Pesapal: Return payment link in response and explain user needs to click it. "
        "For MoMo: Explain user will get prompt on their phone. "
        "\n\n"
        "Always check payment method availability before offering options to users."
    ),
    model="gpt-5-nano",
    output_type=SubscriptionOutput,
    reasoning_effort="low",
    tools=[
        get_subscription_plans_tool,
        get_payment_methods_tool,
        upgrade_subscription_tool,
        get_subscription_status_tool,
        check_payment_status_tool,
    ],
)

web_access_agent = _build_agent(
    name="Website Access Agent",
    instructions=(
        "Help customers access their orders on the Parcelo website. "
        "When a user wants to see their orders, quotations, or account details on the website, "
        "generate a magic link they can click to log in automatically. "
        "\n\n"
        "Explain that: "
        "1. The link will open their browser "
        "2. They'll be automatically logged in "
        "3. They can view all their orders and quotations "
        "4. The link expires in 1 hour for security "
        "\n\n"
        "Be friendly and reassure them it's secure."
    ),
    model="gpt-5-nano",
    output_type=WebAccessOutput,
    reasoning_effort="low",
    tools=[request_website_access_tool],
)

general_agent = _build_agent(
    name="General Assistant",
    instructions=(
        "Handle general inquiries about Parcelo services, operating hours, contact options, or friendly greetings. "
        "Also handle feedback collection when customers want to share their experience, give ratings, or make suggestions. "
        "\n\n"
        "**For Feedback:**\n"
        "- Ask for rating (1-5 stars) if customer mentions experience\n"
        "- Detect sentiment from feedback text (positive, neutral, negative)\n"
        "- Classify feedback type based on content\n"
        "- Thank customer for feedback\n"
        "- If negative feedback with rating <=2, set requires_follow_up=True\n"
        "\n\n"
        "If information is missing, politely request it."
    ),
    model="gpt-5-nano",
    reasoning_effort="low",
    tools=[collect_feedback_tool],
)


@dataclass
class AgentResult:
    route: AgentRoute
    response_text: str
    action: Optional[str] = None
    payload: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    tool: Optional[str] = None


async def run_agent_workflow(
    *,
    message_text: str,
    customer_id: str,
    session_id: str,
    phone_number: str,
    customer_name: str | None = None,
) -> Dict[str, Any]:
    """Route message through classifier and specialised agents."""

    messages, token_usage = await build_prompt_messages(
        session_id=session_id,
        customer_name=customer_name,
        phone_number=phone_number,
        latest_user_text=message_text,
    )

    conversation_history: List[TResponseInputItem] = [
        {
            "role": msg["role"],
            "content": [
                {
                    "type": "output_text" if msg["role"] == "assistant" else "input_text",
                    "text": msg["content"],
                }
            ],
        }
        for msg in messages
    ]

    classifier_result = await Runner.run(
        classifier_agent,
        input=_append_user_utterance(conversation_history, message_text),
        run_config=_build_run_config("classifier"),
    )

    conversation_history.extend(item.to_input_item() for item in classifier_result.new_items)
    parsed_classifier = classifier_result.final_output.model_dump()
    route = AgentRoute(parsed_classifier["route"])

    if route == AgentRoute.UNSAFE:
        return _format_result(
            AgentResult(
                route=route,
                response_text=(
                    "I’m sorry, but I can’t help with that request. Let me know if there’s something else I can assist with."
                ),
            ),
            token_usage,
        )

    agent = _select_agent(route)
    agent_result = await Runner.run(
        agent,
        input=_append_user_utterance(conversation_history, message_text),
        run_config=_build_run_config(route.value),
    )
    conversation_history.extend(item.to_input_item() for item in agent_result.new_items)

    agent_output = agent_result.final_output
    response_text = getattr(agent_output, "response_text", None) or agent_result.final_output_as(str)
    action = getattr(agent_output, "action", None)
    payload = getattr(agent_output, "payload", None)
    tool = getattr(agent_output, "tool", None)

    return _format_result(
        AgentResult(
            route=route,
            response_text=response_text,
            action=action,
            payload=payload,
            metadata={
                "classifier_reasoning": parsed_classifier.get("reasoning"),
                "agent_name": agent.name,
            },
            tool=tool,
        ),
        token_usage,
    )


def _append_user_utterance(
    history: Sequence[TResponseInputItem], message_text: str
) -> List[TResponseInputItem]:
    augmented = list(history)
    if augmented:
        last = augmented[-1]
        if (
            last.get("role") == "user"
            and isinstance(last.get("content"), list)
            and last["content"]
        ):
            last_part = last["content"][0]
            if (
                isinstance(last_part, dict)
                and last_part.get("type") == "input_text"
                and last_part.get("text") == message_text
            ):
                return augmented
    augmented.append(
        {
            "role": "user",
            "content": [{"type": "input_text", "text": message_text}],
        }
    )
    return augmented


def _build_run_config(agent_label: str) -> RunConfig:
    return RunConfig(
        trace_metadata={
            "__trace_source__": "agent_runner",
            "agent": agent_label,
        }
    )


def _select_agent(route: AgentRoute) -> Agent:
    mapping = {
        AgentRoute.QUOTATION: quotation_agent,
        AgentRoute.WISHLIST: wishlist_agent,
        AgentRoute.PAYMENTS: payments_agent,
        AgentRoute.ORDERS: orders_agent,
        AgentRoute.ESCALATION: escalation_agent,
        AgentRoute.SHIPPING: shipping_agent,
        AgentRoute.SUBSCRIPTION: subscription_agent,
        AgentRoute.WEB_ACCESS: web_access_agent,
        AgentRoute.GENERAL: general_agent,
    }
    return mapping.get(route, general_agent)


def _format_result(result: AgentResult, token_usage: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "intent": result.route.value,
        "response_text": result.response_text.strip() or "Thank you for your message!",
        "action": result.action,
        "metadata": {
            "model": "multi-agent",
            "payload": result.payload,
            "route": result.route.value,
            "classifier_reason": (result.metadata or {}).get("classifier_reasoning"),
            "agent_name": (result.metadata or {}).get("agent_name"),
            "tool": result.tool,
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
    summary_message: Optional[Dict[str, str]] = None
    if summary_text:
        summary_message = {"role": "system", "content": f"Conversation summary:\n{summary_text}"}
        messages.append(summary_message)
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

    prompt_tokens, summary_included, recall_included = _ensure_token_budget(
        messages, recall_messages, summary_message
    )

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


def _ensure_token_budget(
    messages: List[Dict[str, str]],
    recall_messages: Sequence[Dict[str, str]],
    summary_message: Optional[Dict[str, str]],
) -> Tuple[int, bool, bool]:
    prompt_tokens = _count_tokens(messages)

    if prompt_tokens <= MAX_PROMPT_TOKENS:
        summary_included = summary_message in messages if summary_message else False
        recall_included = any(msg in messages for msg in recall_messages)
        return prompt_tokens, summary_included, recall_included

    def _pop_matching(predicate, *, reverse: bool) -> bool:
        indices = range(len(messages) - 1, -1, -1) if reverse else range(len(messages))
        for idx in indices:
            if predicate(messages[idx], idx):
                messages.pop(idx)
                return True
        return False

    while prompt_tokens > MAX_PROMPT_TOKENS and len(messages) > 1:
        removed = False

        # Prefer removing recall messages first as they are auxiliary.
        removed = _pop_matching(lambda msg, _: msg in recall_messages, reverse=True)

        if not removed:
            def _candidate(msg: Dict[str, str], idx: int) -> bool:
                if idx == 0:
                    return False
                if summary_message is not None and msg is summary_message:
                    return False
                return True

            removed = _pop_matching(_candidate, reverse=False)

        if not removed:
            break

        prompt_tokens = _count_tokens(messages)

    if prompt_tokens > MAX_PROMPT_TOKENS:
        logger.warning(
            "Prompt still exceeds token budget",
            extra={
                "prompt_tokens": prompt_tokens,
                "budget": MAX_PROMPT_TOKENS,
            },
        )

    summary_included = summary_message in messages if summary_message else False
    recall_included = any(msg in messages for msg in recall_messages)
    return prompt_tokens, summary_included, recall_included


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
