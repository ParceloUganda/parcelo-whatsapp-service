# 🔄 Agent Workflow & Template Mapping

## 📊 Complete Flow Analysis

This document maps **every agent workflow** to show:
1. When to use **WhatsApp templates** ✅
2. When to use **plain text messages** 💬
3. When to send **media attachments** 📄

---

## 🛒 WORKFLOW 1: Quotation Agent

### **User Journey:**
```
Customer: "I want to buy iPhone 15 from Amazon"
  ↓
Classifier → QUOTATION route
  ↓
Quotation Agent: CreateQuotation tool
  ↓
Next.js API: POST /api/s2s/quotations
  ↓
Scrapes product, calculates costs
  ↓
Generates quotation PDF
  ↓
✅ SEND TEMPLATE: quotation_ready
  📄 WITH DOCUMENT: quotation.pdf
  🔘 Quick Replies:
     - "Add to Cart 🛒"
     - "Save to Wishlist ❤️"
     - "Modify Quote ✏️"
```

**Template Used:** `quotation_ready`  
**Media Type:** Document (PDF)  
**Buttons:** 3 Quick Replies

**Why Template?**
- Professional presentation
- Document attachment for quotation
- Action buttons for immediate response
- Can be sent outside 24-hour window if needed

---

### **Follow-up: Add to Cart**
```
Customer clicks: "Add to Cart 🛒"
  ↓
Webhook receives quick_reply payload
  ↓
Quotation Agent: AddToCart tool
  ↓
Next.js API: POST /api/s2s/carts
  ↓
Items added to cart
  ↓
💬 PLAIN TEXT: "Great! I've added 3 items to your cart..."
```

**No Template Needed:** Conversational response within 24-hour window

---

### **Follow-up: Save to Wishlist**
```
Customer clicks: "Save to Wishlist ❤️"
  ↓
Quotation Agent: AddToWishlist tool
  ↓
Next.js API: POST /api/quotations/{id}/add-to-wishlist
  ↓
💬 PLAIN TEXT: "Saved! I'll notify you if prices drop..."
```

**No Template Needed:** Simple confirmation

---

## 💳 WORKFLOW 2: Payments Agent

### **User Journey: Initiate Payment**
```
Customer: "I want to pay for my order"
  ↓
Classifier → PAYMENTS route
  ↓
Payments Agent: InitiatePayment tool
  ↓
Next.js API: POST /api/payment/initiate
  ↓
Creates payment intent (Pesapal/MoMo)
  ↓
✅ SEND TEMPLATE: payment_request
  🔘 Buttons:
     - "Pay Now 💳" (URL to Pesapal)
     - "Pay with MoMo 📱" (Quick Reply)
     - "Need Help ❓" (Quick Reply)
```

**Template Used:** `payment_request`  
**Buttons:** 1 URL + 2 Quick Replies

**Why Template?**
- Critical transaction flow
- Payment link must be clickable
- Clear call-to-action
- Professional trust-building

---

### **User Journey: Payment Confirmed**
```
Webhook from Pesapal/MoMo: Payment successful
  ↓
Next.js processes payment
  ↓
Generates receipt PDF
  ↓
✅ SEND TEMPLATE: payment_confirmed
  📄 WITH DOCUMENT: receipt.pdf
  🔘 Quick Replies:
     - "Track Order 📦"
     - "View Details 📋"
```

**Template Used:** `payment_confirmed`  
**Media Type:** Document (Receipt PDF)  
**Buttons:** 2 Quick Replies

**Why Template?**
- Transaction confirmation (required)
- Receipt attachment (legal requirement)
- Immediate next action (track order)
- Can be sent anytime (not within 24h window)

---

### **User Journey: Check Payment Status**
```
Customer: "Did my payment go through?"
  ↓
Payments Agent: CheckPaymentStatus tool
  ↓
Next.js API: GET /api/payment/status
  ↓
💬 PLAIN TEXT: "Your payment of 350,000 UGX was successful..."
```

**No Template Needed:** Conversational query response

---

## 📦 WORKFLOW 3: Orders Agent

### **User Journey: Create Order**
```
Customer: "I'm ready to checkout"
  ↓
Classifier → ORDERS route
  ↓
Orders Agent: CreateOrderFromCart tool
  ↓
Next.js API: POST /api/s2s/orders
  ↓
Creates order from cart
  ↓
💬 PLAIN TEXT: "Order created! Order #ORD-2025-001..."
  (Then automatically triggers payment_request template)
```

**No Template for Order Creation:** Leads directly to payment flow

---

### **User Journey: Order Shipped**
```
Admin marks order as shipped in dashboard
  ↓
Next.js webhook triggers notification
  ↓
✅ SEND TEMPLATE: order_shipped
  🔘 Buttons:
     - "Track Package 📍" (URL to carrier)
     - "Update Address 📮" (Quick Reply)
```

**Template Used:** `order_shipped`  
**Buttons:** 1 URL + 1 Quick Reply

**Why Template?**
- Important status update
- Tracking link must be clickable
- Sent outside 24-hour window
- High customer expectation

---

### **User Journey: Order Delivered**
```
Carrier confirms delivery
  ↓
Next.js updates order status
  ↓
✅ SEND TEMPLATE: order_delivered
  🔘 Quick Replies:
     - "⭐⭐⭐⭐⭐ Excellent"
     - "⭐⭐⭐⭐ Good"
     - "⭐⭐⭐ Average"
```

**Template Used:** `order_delivered`  
**Buttons:** 3 Quick Replies (star ratings)

**Why Template?**
- Completion milestone
- Immediate feedback collection
- Professional presentation
- Sent outside 24-hour window

---

### **User Journey: Track Order**
```
Customer: "Where is my order?"
  ↓
Orders Agent: GetOrderDetails tool
  ↓
Next.js API: GET /api/s2s/orders/{id}
  ↓
💬 PLAIN TEXT: "Your order #ORD-2025-001 is in transit..."
  + Tracking link
```

**No Template Needed:** Conversational query within 24h window

---

## 🚨 WORKFLOW 4: Escalation Agent

### **User Journey: Angry Customer**
```
Customer: "This is ridiculous! I want my money back NOW!"
  ↓
Classifier → ESCALATION route
  ↓
Escalation Agent detects:
  - Sentiment: ANGRY
  - Category: refund_request
  - Priority: URGENT
  ↓
Escalation Agent: EscalateToHuman tool
  ↓
Next.js API: POST /api/support/escalate
  ↓
Creates support_ticket record
  ↓
✅ SEND TEMPLATE: escalation_created
  🔘 Quick Replies:
     - "Check Status 📋"
     - "Add Info ➕"
```

**Template Used:** `escalation_created`  
**Buttons:** 2 Quick Replies

**Why Template?**
- Critical customer service moment
- Professional reassurance
- Clear ticket number
- Action buttons for transparency

---

### **User Journey: Human Agent Responds**
```
Human agent replies in support dashboard
  ↓
Next.js webhook sends notification
  ↓
✅ SEND TEMPLATE: agent_response
  🔘 Quick Replies:
     - "Reply to Agent 💬"
     - "Close Ticket ✅"
```

**Template Used:** `agent_response`  
**Buttons:** 2 Quick Replies

**Why Template?**
- Clear distinction from bot
- Agent name visible
- Can be sent anytime (agent may respond hours later)
- Professional presentation

---

## 💰 WORKFLOW 5: Subscription Agent

### **User Journey: Upgrade Subscription**
```
Customer: "I want to upgrade to Standard plan"
  ↓
Classifier → SUBSCRIPTION route
  ↓
Subscription Agent:
  1. GetSubscriptionPlans tool
  2. GetPaymentMethods tool
  ↓
💬 PLAIN TEXT: "Here are our plans:..."
  (Shows plans with prices)
  ↓
Customer: "I'll take Standard monthly"
  ↓
Subscription Agent: UpgradeSubscription tool
  ↓
Next.js API: POST /api/subscription/checkout
  ↓
✅ SEND TEMPLATE: payment_request (same as orders)
  ↓
Payment confirmed
  ↓
✅ SEND TEMPLATE: subscription_confirmed
  📄 WITH DOCUMENT: subscription_receipt.pdf
  🔘 Quick Replies:
     - "View Benefits 🎁"
     - "Manage Plan ⚙️"
```

**Templates Used:**
1. `payment_request` (for payment)
2. `subscription_confirmed` (for activation)

**Why Templates?**
- Transaction flow (payment)
- Receipt document required
- Important milestone confirmation
- Upsell opportunity with benefits button

---

### **User Journey: Check Subscription Status**
```
Customer: "What's my current plan?"
  ↓
Subscription Agent: GetSubscriptionStatus tool
  ↓
Next.js API: GET /api/subscription/summary
  ↓
💬 PLAIN TEXT: "You're on Standard plan..."
```

**No Template Needed:** Simple status query

---

## 🔐 WORKFLOW 6: Web Access Agent

### **User Journey: Magic Link Request**
```
Customer: "Can I see my orders on the website?"
  ↓
Classifier → WEB_ACCESS route
  ↓
Web Access Agent: RequestWebsiteAccess tool
  ↓
Next.js API: POST /api/auth/generate-magic-link
  ↓
Creates magic_auth_tokens record
  ↓
✅ SEND TEMPLATE: magic_link_access
  🔘 Button:
     - "Open Account 🌐" (URL to magic link)
```

**Template Used:** `magic_link_access`  
**Buttons:** 1 URL Button

**Why Template?**
- Security-critical (authentication)
- Link must be clickable
- Professional presentation builds trust
- Fast-track approval (auth category)

---

## 💬 WORKFLOW 7: General Agent (Feedback)

### **User Journey: Customer Leaves Feedback**
```
Customer: "5 stars! Great service!"
  ↓
Classifier → GENERAL route
  ↓
General Agent: CollectFeedback tool
  ↓
Next.js API: POST /api/feedback/collect
  ↓
💬 PLAIN TEXT: "Thank you for the 5-star rating! ⭐⭐⭐⭐⭐"
```

**No Template Needed:** Conversational thank you within 24h window

---

### **User Journey: Negative Feedback → Auto-Escalate**
```
Customer: "1 star, item arrived broken"
  ↓
General Agent: CollectFeedback tool
  - Sentiment: NEGATIVE
  - Rating: 1
  - Auto-escalate: TRUE
  ↓
Next.js API: POST /api/feedback/collect
  ↓
Automatically creates support_ticket
  ↓
✅ SEND TEMPLATE: escalation_created
```

**Template Used:** `escalation_created` (same as manual escalation)

---

## 📍 WORKFLOW 8: Shipping Agent

### **User Journey: Track Shipment**
```
Customer: "Where is my package?"
  ↓
Classifier → SHIPPING route
  ↓
Shipping Agent: TrackShipment tool
  ↓
Next.js API: GET /api/shipments/{id}
  ↓
💬 PLAIN TEXT: "Your package is in transit..."
  + Tracking link
```

**No Template Needed:** Conversational response

---

### **Proactive: Shipping Delayed (Optional)**
```
Carrier reports delay
  ↓
Next.js webhook triggers notification
  ↓
✅ SEND TEMPLATE: shipping_delayed
  🔘 Quick Replies:
     - "Get Update 📞"
     - "Cancel Order ❌"
```

**Template Used:** `shipping_delayed` (Optional - future)  
**Why?** Proactive service recovery

---

## 🛍️ WORKFLOW 9: Wishlist Agent

### **User Journey: View Wishlist**
```
Customer: "Show my saved items"
  ↓
Classifier → WISHLIST route
  ↓
Wishlist Agent: GetWishlist tool
  ↓
Next.js API: GET /api/s2s/wishlists
  ↓
💬 PLAIN TEXT: "You have 5 items saved:..."
```

**No Template Needed:** List response

---

### **Proactive: Price Drop Alert (Optional)**
```
Cron job detects price drop on wishlist item
  ↓
Next.js triggers notification
  ↓
✅ SEND TEMPLATE: wishlist_price_drop
  🖼️ WITH IMAGE: Product image
  🔘 Quick Replies:
     - "Add to Cart 🛒"
     - "View Item 👁️"
     - "Remove ❌"
```

**Template Used:** `wishlist_price_drop` (Optional - future)  
**Media Type:** Image (product photo)

---

## 📊 Summary Table

| Workflow | Template Needed? | Media Type | Buttons | Priority |
|----------|-----------------|------------|---------|----------|
| **Quotation Created** | ✅ YES | PDF Document | 3 Quick | 🔴 CRITICAL |
| **Payment Request** | ✅ YES | None | 1 URL + 2 Quick | 🔴 CRITICAL |
| **Payment Confirmed** | ✅ YES | PDF Receipt | 2 Quick | 🔴 CRITICAL |
| **Order Shipped** | ✅ YES | None | 1 URL + 1 Quick | 🟡 HIGH |
| **Order Delivered** | ✅ YES | None | 3 Quick (ratings) | 🟡 HIGH |
| **Escalation Created** | ✅ YES | None | 2 Quick | 🔴 CRITICAL |
| **Agent Response** | ✅ YES | None | 2 Quick | 🟡 HIGH |
| **Subscription Confirmed** | ✅ YES | PDF Receipt | 2 Quick | 🟡 HIGH |
| **Magic Link** | ✅ YES | None | 1 URL | 🔴 CRITICAL |
| **Cart Reminder** | ⚠️ OPTIONAL | None | 3 Quick | 🟢 LOW |
| **Price Drop Alert** | ⚠️ OPTIONAL | Image | 3 Quick | 🟢 LOW |
| **Shipping Delayed** | ⚠️ OPTIONAL | None | 2 Quick | 🟢 LOW |
| **Quotation Inquiry** | ❌ NO | - | - | - |
| **Order Status Query** | ❌ NO | - | - | - |
| **Feedback Thank You** | ❌ NO | - | - | - |
| **General Questions** | ❌ NO | - | - | - |

---

## 🎯 Template vs Plain Text Decision Tree

```
┌─────────────────────────────┐
│ Agent generates response    │
└────────────┬────────────────┘
             │
             ▼
      ┌──────────────┐
      │ Is this a    │
      │ transactional│
      │ event?       │
      └──────┬───────┘
             │
        ┌────┴────┐
        │         │
       YES       NO
        │         │
        ▼         ▼
  ┌─────────┐  ┌──────────┐
  │ Outside │  │ Within   │
  │ 24-hour │  │ 24-hour  │
  │ window? │  │ window?  │
  └────┬────┘  └────┬─────┘
       │            │
   ┌───┴───┐       YES
   │       │        │
  YES     NO        ▼
   │       │   ┌──────────┐
   ▼       ▼   │ Plain    │
┌────────┐ ┌──────────┐  │ Text     │
│Template│ │Does need │  │ Message  │
│REQUIRED│ │document/ │  └──────────┘
└────────┘ │clickable?│
           └────┬─────┘
                │
           ┌────┴────┐
           │         │
          YES       NO
           │         │
           ▼         ▼
      ┌────────┐  ┌──────────┐
      │Template│  │ Plain    │
      │(better │  │ Text OK  │
      │UX)     │  └──────────┘
      └────────┘
```

---

## 📝 Implementation Checklist

### **Before Writing Code:**
- [ ] Create all CRITICAL templates in Meta Business Manager
- [ ] Submit for approval (wait 24-48 hours)
- [ ] Test each approved template with test phone number
- [ ] Document template names and parameter order

### **After Template Approval:**
- [ ] Update `agent_runner.py` with template decision logic
- [ ] Create `send_whatsapp_template()` function in Luminous service
- [ ] Create `send_whatsapp_media()` function for documents
- [ ] Map quick reply payloads to agent actions
- [ ] Test end-to-end flows with templates

### **Media/Document Requirements:**
- [ ] Set up CDN for quotation PDFs
- [ ] Set up CDN for receipt PDFs
- [ ] Set up CDN for subscription receipts
- [ ] Ensure all URLs are HTTPS and publicly accessible
- [ ] Test document downloads on mobile devices

---

## 🚀 Next Steps

1. **Week 1:** Submit 5 CRITICAL templates to Meta
2. **Week 2:** While waiting for approval, prepare document generation (PDFs)
3. **Week 3:** Test approved templates, implement sending logic
4. **Week 4:** Launch with templates, monitor engagement

**DO NOT write template-sending code until templates are approved by Meta! ✅**
