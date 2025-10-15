"""Tool execution handlers for agent tools."""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx
from config import get_settings
from utils.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


# ============================================================================
# ESCALATION HANDLER
# ============================================================================

async def handle_escalate_to_human(
    payload: Dict[str, Any],
    session_id: str,
    customer_phone: str,
    conversation_history: List[Dict],
) -> str:
    """
    Execute escalation to human agent.
    Creates support ticket with full context.
    """
    # Get last 10 messages for context
    last_messages = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
    
    # Create conversation summary
    summary_lines = []
    for msg in last_messages[-5:]:
        role = "Customer" if msg.get("role") == "user" else "Bot"
        text = msg.get("content", "")[:100]
        summary_lines.append(f"{role}: {text}")
    summary = "\n".join(summary_lines)
    
    # Extract keywords
    conversation_text = " ".join([msg.get("content", "").lower() for msg in conversation_history])
    keywords = []
    for keyword in ["refund", "broken", "damaged", "lost", "angry", "frustrated", "manager", "complaint"]:
        if keyword in conversation_text:
            keywords.append(keyword)
    
    # Generate subject
    category = payload.get("category", "other")
    sentiment = payload.get("sentiment", "neutral")
    subject_map = {
        "payment_issue": "Payment Issue",
        "delivery_problem": "Delivery Problem",
        "refund_request": "Refund Request",
        "complaint": "Customer Complaint",
        "technical_issue": "Technical Issue",
        "product_inquiry": "Product Inquiry",
        "other": "Support Request"
    }
    subject = subject_map.get(category, "Support Request")
    if sentiment == "angry":
        subject = f"🚨 URGENT: {subject}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.nextjs_api_url}/api/support/escalate",
                json={
                    "customer_id": payload["customer_id"],
                    "source_type": "whatsapp",
                    "source_reference_id": session_id,
                    "source_phone_number": customer_phone,
                    "subject": subject,
                    "escalation_reason": payload["reason"],
                    "escalation_category": payload["category"],
                    "priority": payload["priority"],
                    "status": "open",
                    "bot_detected_sentiment": payload["sentiment"],
                    "customer_journey_stage": payload.get("journey_stage"),
                    "metadata": {
                        "conversation_summary": summary,
                        "conversation_history": last_messages,
                        "keywords_detected": keywords,
                        "bot_confidence": 0.95,
                        "escalation_timestamp": datetime.utcnow().isoformat(),
                    }
                },
                headers={
                    "X-Service-Token": settings.service_secret,
                    "Content-Type": "application/json"
                },
                timeout=15.0
            )
            
            if response.status_code == 200:
                result = response.json()
                ticket_number = result.get("ticket_number", "Unknown")
                
                logger.info(
                    "Escalation created successfully",
                    extra={
                        "ticket_id": result.get("ticket_id"),
                        "customer_id": payload["customer_id"],
                        "category": payload["category"],
                        "sentiment": payload["sentiment"],
                        "priority": payload["priority"]
                    }
                )
                
                # Format response based on sentiment
                if payload["sentiment"] == "angry":
                    return (
                        f"🙋 I understand you're frustrated, and I apologize for the inconvenience.\n\n"
                        f"I've immediately connected you with our support team.\n\n"
                        f"📋 Ticket: {ticket_number}\n"
                        f"⏱️ A human agent will respond within 15 minutes.\n\n"
                        f"Thank you for your patience."
                    )
                else:
                    return (
                        f"🙋 I've connected you with our support team for assistance.\n\n"
                        f"📋 Your ticket number: {ticket_number}\n"
                        f"⏱️ An agent will respond shortly.\n\n"
                        f"Is there anything else I can help you with while you wait?"
                    )
            else:
                logger.error(f"Escalation failed: {response.status_code} - {response.text}")
                return (
                    "I apologize, but I'm having trouble connecting you to our support team right now. "
                    "Please call us at +256-XXX-XXXXXX for immediate assistance."
                )
    
    except Exception as e:
        logger.error(f"Escalation error: {e}")
        return (
            "I apologize for the technical issue. "
            "Please contact support@parceloug.com or call +256-XXX-XXXXXX."
        )


# ============================================================================
# FEEDBACK HANDLER
# ============================================================================

async def handle_collect_feedback(
    payload: Dict[str, Any],
    session_id: str,
    customer_phone: str,
) -> str:
    """
    Execute feedback collection.
    Stores feedback in customer_feedback table.
    Auto-escalates if negative feedback with low rating.
    """
    try:
        # Check if negative feedback requires escalation
        should_escalate = False
        rating = payload.get("rating")
        sentiment = payload.get("sentiment", "neutral")
        
        if sentiment == "negative" and rating and rating <= 2:
            should_escalate = True
            payload["requires_follow_up"] = True
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.nextjs_api_url}/api/feedback/collect",
                json={
                    "customer_id": payload["customer_id"],
                    "source_type": "whatsapp",
                    "source_reference_id": session_id,
                    "feedback_type": payload["feedback_type"],
                    "feedback_text": payload["feedback_text"],
                    "sentiment": payload["sentiment"],
                    "rating": payload.get("rating"),
                    "order_id": payload.get("order_id"),
                    "journey_stage": payload.get("journey_stage", "other"),
                    "requires_follow_up": payload.get("requires_follow_up", False),
                    "metadata": {
                        "source_phone": customer_phone,
                        "collected_at": datetime.utcnow().isoformat(),
                    }
                },
                headers={
                    "X-Service-Token": settings.service_secret,
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                
                logger.info(
                    "Feedback collected successfully",
                    extra={
                        "feedback_id": result.get("feedback_id"),
                        "customer_id": payload["customer_id"],
                        "feedback_type": payload["feedback_type"],
                        "sentiment": payload["sentiment"],
                        "rating": payload.get("rating")
                    }
                )
                
                # Format response based on sentiment and escalation
                if should_escalate:
                    return (
                        f"Thank you for your honest feedback. I'm sorry to hear about your experience.\n\n"
                        f"I've escalated this to our management team for immediate review.\n"
                        f"Someone will reach out to you within 24 hours to make this right.\n\n"
                        f"We value your business and want to ensure your satisfaction."
                    )
                elif sentiment == "positive":
                    stars = "⭐" * (rating if rating else 5)
                    return (
                        f"Thank you so much for the {rating}-star rating! {stars}\n\n"
                        f"We're thrilled to hear you had a great experience.\n"
                        f"Your feedback helps us continue providing excellent service!"
                    )
                else:
                    return (
                        f"Thank you for your feedback! We appreciate you taking the time to share your thoughts.\n\n"
                        f"Your input helps us improve our service. 🙏"
                    )
            else:
                logger.error(f"Feedback collection failed: {response.status_code} - {response.text}")
                return "Thank you for your feedback! It has been noted."
    
    except Exception as e:
        logger.error(f"Feedback collection error: {e}")
        return "Thank you for your feedback! We appreciate your input."


# ============================================================================
# SUBSCRIPTION HANDLERS
# ============================================================================

async def handle_get_subscription_plans(payload: Dict[str, Any]) -> str:
    """Fetch and format current subscription plans"""
    from services.agent_runner import get_subscription_plans
    
    result = await get_subscription_plans()
    plans = result.get("plans", [])
    
    if not plans:
        return "Unable to fetch subscription plans at the moment. Please try again shortly."
    
    plans_text = "📋 *Parcelo Subscription Plans:*\n\n"
    
    for plan in plans:
        plan_name = plan.get("name", "Unknown Plan")
        
        if plan.get("is_free"):
            plans_text += f"*{plan_name}* - FREE\n"
        elif plan.get("monthly"):
            monthly_price = plan["monthly"]["price_ugx"]
            plans_text += f"*{plan_name}* - {monthly_price:,} UGX/month\n"
            
            if plan.get("yearly"):
                yearly_price = plan["yearly"]["price_ugx"]
                discount = plan["yearly"].get("discount_percent", 0)
                plans_text += f"  _or {yearly_price:,} UGX/year ({discount}% off)_\n"
        
        plans_text += f"  • {plan['shopping_requests']} requests/month\n"
        plans_text += f"  • {plan['service_fee_percent']}% service fee\n"
        
        if plan['shipping_discount_percent'] > 0:
            plans_text += f"  • {plan['shipping_discount_percent']}% shipping discount\n"
        
        if plan['minimum_spend_usd'] > 0:
            plans_text += f"  • ${plan['minimum_spend_usd']} minimum order\n"
        else:
            plans_text += f"  • No minimum order\n"
        
        plans_text += "\n"
    
    plans_text += "Reply with the plan you want (e.g., 'standard monthly')"
    
    return plans_text


async def handle_get_payment_methods(payload: Dict[str, Any]) -> str:
    """Fetch and format available payment methods"""
    from services.agent_runner import get_available_payment_methods
    
    result = await get_available_payment_methods()
    methods = result.get("available_methods", [])
    
    if not methods:
        return "Payment methods are currently unavailable. Please contact our support team."
    
    methods_text = "💳 *Available Payment Methods:*\n\n"
    
    for method in methods:
        icon = method.get("icon", "💰")
        name = method.get("name", "Unknown")
        description = method.get("description", "")
        
        methods_text += f"{icon} *{name}*\n"
        methods_text += f"  {description}\n\n"
    
    if len(methods) > 1:
        methods_text += "Reply with your choice:\n• 'momo' for Mobile Money\n• 'card' for Card Payment"
    
    return methods_text


# ============================================================================
# WEB ACCESS HANDLER
# ============================================================================

async def handle_request_website_access(payload: Dict[str, Any]) -> str:
    """Generate magic link for website access"""
    from services.agent_runner import generate_magic_link_for_customer
    
    result = await generate_magic_link_for_customer(
        customer_id=payload["customer_id"],
        phone_number=payload["phone_number"],
    )
    
    if result.get("success"):
        magic_link = result["magic_link"]
        
        return (
            f"🔐 *Access Your Parcelo Account*\n\n"
            f"Click here to view your orders:\n"
            f"{magic_link}\n\n"
            f"⏰ This link expires in 1 hour\n"
            f"🔒 Secure login - no password needed\n\n"
            f"Once you click the link:\n"
            f"• Your browser will open automatically\n"
            f"• You'll be logged into your account\n"
            f"• You can view all your orders and quotations\n\n"
            f"Need help? Just reply and I'll assist you!"
        )
    else:
        return (
            "Sorry, I couldn't generate your access link right now. "
            "Please try again in a moment, or contact our support team."
        )


# ============================================================================
# MAIN TOOL EXECUTION HANDLER
# ============================================================================

async def execute_agent_tool(
    tool_name: str,
    payload: Dict[str, Any],
    agent_response_text: str,
    session_id: str = None,
    customer_phone: str = None,
    conversation_history: List[Dict] = None,
) -> str:
    """
    Main dispatcher for tool execution.
    Returns formatted message to send to user.
    """
    
    # Escalation tools
    if tool_name == "EscalateToHuman":
        return await handle_escalate_to_human(
            payload, session_id, customer_phone, conversation_history or []
        )
    
    # Feedback tools
    elif tool_name == "CollectFeedback":
        return await handle_collect_feedback(
            payload, session_id, customer_phone
        )
    
    # Subscription tools
    elif tool_name == "GetSubscriptionPlans":
        return await handle_get_subscription_plans(payload)
    
    elif tool_name == "GetPaymentMethods":
        return await handle_get_payment_methods(payload)
    
    # Web access tools
    elif tool_name == "RequestWebsiteAccess":
        return await handle_request_website_access(payload)
    
    # Default: return agent's response text
    return agent_response_text
