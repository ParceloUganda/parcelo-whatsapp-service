# 📱 WhatsApp Business Templates Strategy for Parcelo

## 🎯 Overview

This document outlines the **WhatsApp Business Message Templates** needed for Parcelo's agent system. These templates must be created in Meta Business Manager and **approved by Meta before use**.

**Key Principles:**
1. Templates for high-value transactional messages (confirmations, status updates)
2. Plain text for conversational responses
3. Media attachments for documents (quotations, receipts, invoices)
4. Agent decides dynamically when to use templates vs plain messages

---

## 📋 Agent Workflows Analysis

Based on `agent_runner.py`, we have **10 agent routes**:

| Agent | Purpose | Template Needed? |
|-------|---------|-----------------|
| **Quotation** | Create price quotes, add to cart/wishlist | ✅ YES |
| **Wishlist** | Manage saved items | ⚠️ OPTIONAL |
| **Payments** | Initiate payments, check status | ✅ YES |
| **Orders** | Track orders, order status | ✅ YES |
| **Escalation** | Connect to human agent | ✅ YES |
| **Shipping** | Track shipments | ✅ YES |
| **Subscription** | Upgrade plans, manage billing | ✅ YES |
| **Web Access** | Send magic links | ✅ YES |
| **General** | FAQ, feedback collection | ❌ NO (plain text) |
| **Unsafe** | Blocked content | ❌ NO (plain text) |

---

## 🎨 Template Categories

### **CATEGORY 1: TRANSACTIONAL (Utility)**
High-priority templates for business-critical flows.

### **CATEGORY 2: MARKETING (Marketing)**
Optional templates for promotional content.

### **CATEGORY 3: AUTHENTICATION (Authentication)**
OTP and magic link templates.

---

## 📝 Required Templates (15 Total)

---

### **1. QUOTATION_READY** (Utility)
**When:** Agent creates quotation successfully  
**Contains:** Quotation summary with document attachment

**Components:**
- **Header:** Image/Document (quotation PDF)
- **Body:** Quotation details with variables
- **Buttons:** Quick replies

**Template JSON for Meta:**
```json
{
  "name": "quotation_ready",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "DOCUMENT"
    },
    {
      "type": "BODY",
      "text": "✅ Your quotation is ready!\n\n📦 Items: {{1}}\n💰 Total Cost: {{2}} UGX\n🚚 Est. Delivery: {{3}}\n\nReview the attached quotation document for full details.",
      "example": {
        "body_text": [
          ["3 items", "450,000", "7-10 business days"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "Add to Cart 🛒"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Save to Wishlist ❤️"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Modify Quote ✏️"
        }
      ]
    }
  ]
}
```

**When to send:**
```python
# After quotation_agent creates quotation
await send_template(
    phone=customer_phone,
    template_name="quotation_ready",
    document_url=quotation_pdf_url,
    body_params=[
        f"{item_count} items",
        f"{total_ugx:,}",
        f"{delivery_days} business days"
    ]
)
```

---

### **2. PAYMENT_REQUEST** (Utility)
**When:** Customer needs to pay for order  
**Contains:** Payment link with amount

**Template JSON:**
```json
{
  "name": "payment_request",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "💳 Payment Required"
    },
    {
      "type": "BODY",
      "text": "Hi {{1}},\n\nYour order #{{2}} is ready for payment.\n\n💰 Amount: {{3}} UGX\n📦 Items: {{4}}\n\nComplete payment to proceed with shipping.",
      "example": {
        "body_text": [
          ["John", "ORD-2025-001", "350,000", "2 items"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "URL",
          "text": "Pay Now 💳",
          "url": "{{1}}",
          "example": ["https://pay.pesapal.com/iframe/PTC-XXX"]
        },
        {
          "type": "QUICK_REPLY",
          "text": "Pay with MoMo 📱"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Need Help ❓"
        }
      ]
    }
  ]
}
```

---

### **3. PAYMENT_CONFIRMED** (Utility)
**When:** Payment successful  
**Contains:** Receipt document

**Template JSON:**
```json
{
  "name": "payment_confirmed",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "DOCUMENT"
    },
    {
      "type": "BODY",
      "text": "✅ Payment Received!\n\nOrder: #{{1}}\nAmount: {{2}} UGX\nPaid: {{3}}\n\n🚚 Your order is now being prepared for shipping.\n\nDownload your receipt attached above.",
      "example": {
        "body_text": [
          ["ORD-2025-001", "350,000", "Oct 15, 2025 2:30 PM"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "Track Order 📦"
        },
        {
          "type": "QUICK_REPLY",
          "text": "View Details 📋"
        }
      ]
    }
  ]
}
```

---

### **4. ORDER_SHIPPED** (Utility)
**When:** Order dispatched  
**Contains:** Tracking information

**Template JSON:**
```json
{
  "name": "order_shipped",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "📦 Your Order is On the Way!"
    },
    {
      "type": "BODY",
      "text": "Great news! Order #{{1}} has been shipped.\n\n📍 Tracking: {{2}}\n🚚 Carrier: {{3}}\n📅 Est. Delivery: {{4}}\n\nTrack your package in real-time.",
      "example": {
        "body_text": [
          ["ORD-2025-001", "TRK-123456789", "DHL Uganda", "Oct 22, 2025"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "URL",
          "text": "Track Package 📍",
          "url": "{{1}}",
          "example": ["https://track.dhl.com/TRK-123456789"]
        },
        {
          "type": "QUICK_REPLY",
          "text": "Update Address 📮"
        }
      ]
    }
  ]
}
```

---

### **5. ORDER_DELIVERED** (Utility)
**When:** Order delivered successfully  
**Contains:** Feedback request

**Template JSON:**
```json
{
  "name": "order_delivered",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "✅ Delivered Successfully!"
    },
    {
      "type": "BODY",
      "text": "Your order #{{1}} was delivered on {{2}}.\n\n📦 Items: {{3}}\n\nWe hope you love your purchase! Please take a moment to rate your experience.",
      "example": {
        "body_text": [
          ["ORD-2025-001", "Oct 20, 2025", "2 items"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "⭐⭐⭐⭐⭐ Excellent"
        },
        {
          "type": "QUICK_REPLY",
          "text": "⭐⭐⭐⭐ Good"
        },
        {
          "type": "QUICK_REPLY",
          "text": "⭐⭐⭐ Average"
        }
      ]
    }
  ]
}
```

---

### **6. ESCALATION_CREATED** (Utility)
**When:** Customer escalated to human agent  
**Contains:** Ticket number and response time

**Template JSON:**
```json
{
  "name": "escalation_created",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "🙋 Connected to Support Team"
    },
    {
      "type": "BODY",
      "text": "I've created a support ticket for you.\n\n🎫 Ticket: {{1}}\n⏱️ Priority: {{2}}\n👤 Agent: Assigning...\n\nA human agent will respond within {{3}}.",
      "example": {
        "body_text": [
          ["TKT-2025-001", "High", "15 minutes"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "Check Status 📋"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Add Info ➕"
        }
      ]
    }
  ]
}
```

---

### **7. AGENT_RESPONSE** (Utility)
**When:** Human agent responds to ticket  
**Contains:** Agent message

**Template JSON:**
```json
{
  "name": "agent_response",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "👤 Support Agent Reply"
    },
    {
      "type": "BODY",
      "text": "{{1}} from Parcelo support:\n\n{{2}}\n\nTicket: {{3}}",
      "example": {
        "body_text": [
          ["Sarah", "I've reviewed your case and issued a full refund. You should see it in 3-5 business days.", "TKT-2025-001"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "Reply to Agent 💬"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Close Ticket ✅"
        }
      ]
    }
  ]
}
```

---

### **8. SUBSCRIPTION_CONFIRMED** (Utility)
**When:** Subscription upgrade successful  
**Contains:** Plan details and receipt

**Template JSON:**
```json
{
  "name": "subscription_confirmed",
  "language": "en",
  "category": "UTILITY",
  "components": [
    {
      "type": "HEADER",
      "format": "DOCUMENT"
    },
    {
      "type": "BODY",
      "text": "🎉 Welcome to {{1}}!\n\n✅ Subscription Active\n💰 {{2}} UGX/{{3}}\n📅 Renews: {{4}}\n\nYour upgraded benefits are now active. Receipt attached above.",
      "example": {
        "body_text": [
          ["Parcelo Plus", "51,900", "month", "Nov 15, 2025"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "View Benefits 🎁"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Manage Plan ⚙️"
        }
      ]
    }
  ]
}
```

---

### **9. MAGIC_LINK** (Authentication)
**When:** Customer requests website access  
**Contains:** Secure login link

**Template JSON:**
```json
{
  "name": "magic_link_access",
  "language": "en",
  "category": "AUTHENTICATION",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "🔐 Website Access Link"
    },
    {
      "type": "BODY",
      "text": "Click the link below to access your Parcelo account:\n\n⏰ Expires in 1 hour\n🔒 Secure automatic login\n\nYou'll be able to view all your orders, quotations, and account details.",
      "example": {
        "body_text": [[]]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "URL",
          "text": "Open Account 🌐",
          "url": "{{1}}",
          "example": ["https://parceloug.com/auth/magic?token=abc123"]
        }
      ]
    }
  ]
}
```

---

### **10. CART_REMINDER** (Marketing - Optional)
**When:** Items in cart for 24+ hours  
**Contains:** Cart summary

**Template JSON:**
```json
{
  "name": "cart_reminder",
  "language": "en",
  "category": "MARKETING",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "🛒 Items Waiting in Your Cart"
    },
    {
      "type": "BODY",
      "text": "Hi {{1}}! You have {{2}} items in your cart:\n\n💰 Total: {{3}} UGX\n\nComplete your order before prices change or items go out of stock!",
      "example": {
        "body_text": [
          ["John", "3", "450,000"]
        ]
      }
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "QUICK_REPLY",
          "text": "Checkout Now 💳"
        },
        {
          "type": "QUICK_REPLY",
          "text": "View Cart 🛒"
        },
        {
          "type": "QUICK_REPLY",
          "text": "Clear Cart 🗑️"
        }
      ]
    }
  ]
}
```

---

### **11-15. Additional Templates (Lower Priority)**

11. **WISHLIST_PRICE_DROP** - When saved item price decreases
12. **SHIPPING_DELAYED** - Delivery delay notification
13. **REFUND_PROCESSED** - Refund confirmation
14. **FEEDBACK_REQUEST** - Post-delivery survey
15. **SUBSCRIPTION_RENEWAL** - Upcoming renewal reminder

---

## 🎬 Agent Decision Logic

### **When Agent Should Use Templates:**

```python
# In your message handler or agent_runner.py

def should_use_template(agent_route: AgentRoute, action: str, context: Dict) -> bool:
    """
    Determine if agent should send template vs plain text.
    """
    
    # ALWAYS use template for these:
    template_required = {
        ("quotation", "quotation_created"): "quotation_ready",
        ("payments", "payment_initiated"): "payment_request",
        ("payments", "payment_confirmed"): "payment_confirmed",
        ("orders", "order_shipped"): "order_shipped",
        ("orders", "order_delivered"): "order_delivered",
        ("escalation", "ticket_created"): "escalation_created",
        ("subscription", "subscription_activated"): "subscription_confirmed",
        ("web_access", "magic_link_generated"): "magic_link_access",
    }
    
    key = (agent_route.value, action)
    return key in template_required

# Usage in message handler:
if should_use_template(agent_route, action, context):
    template_name = get_template_name(agent_route, action)
    await send_whatsapp_template(
        phone=customer_phone,
        template_name=template_name,
        params=extract_template_params(context),
        media_url=context.get("media_url")  # For documents
    )
else:
    # Plain text message
    await send_whatsapp_text(
        phone=customer_phone,
        message=agent_response_text
    )
```

---

## 📤 Sending Templates via Luminous API

### **Text-Only Template:**
```bash
curl -X POST {{luminous_base_url}}/api/send/template \
-H 'Authorization: Bearer {{luminous_api_key}}' \
-H 'Content-Type: application/json' \
-d '{
  "phone": "256700123456",
  "template": {
    "name": "escalation_created",
    "language": {
      "code": "en"
    },
    "components": [
      {
        "type": "body",
        "parameters": [
          {"type": "text", "text": "TKT-2025-001"},
          {"type": "text", "text": "High"},
          {"type": "text", "text": "15 minutes"}
        ]
      },
      {
        "type": "button",
        "sub_type": "quick_reply",
        "index": "0",
        "parameters": [
          {"type": "payload", "payload": "check_ticket_status"}
        ]
      }
    ]
  }
}'
```

### **Template with Document:**
```bash
curl -X POST {{luminous_base_url}}/api/send/template \
-H 'Authorization: Bearer {{luminous_api_key}}' \
-H 'Content-Type: application/json' \
-d '{
  "phone": "256700123456",
  "template": {
    "name": "quotation_ready",
    "language": {
      "code": "en"
    },
    "components": [
      {
        "type": "header",
        "parameters": [
          {
            "type": "document",
            "document": {
              "link": "https://cdn.parceloug.com/quotations/Q-2025-001.pdf",
              "filename": "Quotation_Q-2025-001.pdf"
            }
          }
        ]
      },
      {
        "type": "body",
        "parameters": [
          {"type": "text", "text": "3 items"},
          {"type": "text", "text": "450,000"},
          {"type": "text", "text": "7-10 business days"}
        ]
      }
    ]
  }
}'
```

### **Sending Media (Receipt, Invoice):**
```bash
curl -X POST {{luminous_base_url}}/api/send/media \
-H 'Authorization: Bearer {{luminous_api_key}}' \
-H 'Content-Type: application/json' \
-d '{
  "phone": "256700123456",
  "media_type": "document",
  "media_url": "https://cdn.parceloug.com/receipts/REC-2025-001.pdf",
  "caption": "Your payment receipt for Order #ORD-2025-001",
  "file_name": "Receipt_ORD-2025-001.pdf"
}'
```

---

## 📊 Template Submission Checklist

### **Phase 1: Create in Meta Business Manager**
1. Log into [Meta Business Manager](https://business.facebook.com)
2. Navigate to WhatsApp Manager → Message Templates
3. Click "Create Template"
4. Fill in template details (name, category, components)
5. Add sample parameters
6. Submit for review

### **Phase 2: Wait for Approval**
- **Utility templates:** Usually approved within 24 hours
- **Marketing templates:** May take 2-5 days
- **Authentication templates:** Usually fast-tracked

### **Phase 3: Test Templates**
```python
# Test each template with real phone number
await test_template(
    template_name="quotation_ready",
    test_phone="256700123456",
    params=["3 items", "450,000", "7-10 days"],
    document_url="https://cdn.parceloug.com/test.pdf"
)
```

### **Phase 4: Integrate into Agent**
- Update `agent_runner.py` decision logic
- Add template sending functions
- Handle quick reply payloads
- Monitor delivery rates

---

## 🎯 Priority Order

### **MUST HAVE (Launch Blockers):**
1. ✅ QUOTATION_READY - Core business flow
2. ✅ PAYMENT_REQUEST - Revenue critical
3. ✅ PAYMENT_CONFIRMED - Trust building
4. ✅ ESCALATION_CREATED - Customer service
5. ✅ MAGIC_LINK - Website access

### **SHOULD HAVE (Post-Launch):**
6. ⚠️ ORDER_SHIPPED - Customer expectations
7. ⚠️ ORDER_DELIVERED - Feedback loop
8. ⚠️ SUBSCRIPTION_CONFIRMED - Upsell flow
9. ⚠️ AGENT_RESPONSE - Support continuity

### **NICE TO HAVE (Future):**
10. 💡 CART_REMINDER - Conversion boost
11. 💡 WISHLIST_PRICE_DROP - Re-engagement
12. 💡 SHIPPING_DELAYED - Proactive service

---

## 🚀 Implementation Roadmap

**Week 1:**
- Create 5 MUST HAVE templates in Meta Business Manager
- Submit for approval
- Set up template testing environment

**Week 2:**
- Implement template decision logic in agent
- Add Luminous template sending functions
- Test with real customer scenarios

**Week 3:**
- Create 4 SHOULD HAVE templates
- Monitor delivery rates and approval status
- Optimize quick reply payloads

**Week 4:**
- Launch with approved templates
- Monitor user engagement with buttons
- Collect feedback for improvements

---

## 📈 Success Metrics

Track these KPIs:
- **Template Delivery Rate:** >95% successful delivery
- **Button Click-Through Rate:** >40% engagement with quick replies
- **Template-to-Conversion:** Track orders from template interactions
- **Customer Satisfaction:** NPS score for template vs plain text users

---

## ⚠️ Important Notes

1. **24-Hour Window:** Plain text messages only work within 24 hours of last customer message. Templates can be sent anytime.

2. **Template Changes:** Any modification requires re-approval from Meta. Plan carefully!

3. **Language Support:** Start with English (`en`). Add local languages (Luganda, Swahili) later.

4. **Quick Reply Payloads:** Must be handled in your webhook. Map payloads to agent actions.

5. **Media URLs:** Must be publicly accessible HTTPS URLs. Consider CDN for documents.

6. **Cost:** Template messages may cost more than plain text. Optimize usage!

---

**DO NOT implement code yet. Submit templates to Meta first, then we'll integrate after approval! ✅**
