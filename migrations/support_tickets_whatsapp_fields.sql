-- ============================================================================
-- Support Tickets WhatsApp Escalation Fields
-- ============================================================================
-- This migration adds WhatsApp-specific fields to the existing support_tickets
-- table to properly track escalations from the WhatsApp bot.
-- ============================================================================

-- Add WhatsApp source tracking columns
ALTER TABLE support_tickets 
ADD COLUMN IF NOT EXISTS source_type TEXT 
  CHECK (source_type IN ('whatsapp', 'web', 'email', 'chat', 'phone')) 
  DEFAULT 'whatsapp',

ADD COLUMN IF NOT EXISTS source_reference_id UUID, -- chat_session_id for WhatsApp
ADD COLUMN IF NOT EXISTS source_phone_number TEXT,

-- Add escalation reason tracking
ADD COLUMN IF NOT EXISTS escalation_reason TEXT,
ADD COLUMN IF NOT EXISTS escalation_category TEXT 
  CHECK (escalation_category IN (
    'payment_issue', 
    'delivery_problem', 
    'product_inquiry', 
    'complaint', 
    'technical_issue', 
    'refund_request', 
    'other'
  )),

-- Add bot intelligence fields
ADD COLUMN IF NOT EXISTS bot_detected_sentiment TEXT 
  CHECK (bot_detected_sentiment IN ('positive', 'neutral', 'negative', 'angry', 'confused')),

ADD COLUMN IF NOT EXISTS customer_journey_stage TEXT
  CHECK (customer_journey_stage IN ('quotation', 'cart', 'payment', 'delivery', 'other')),

-- Add resolution tracking
ADD COLUMN IF NOT EXISTS first_response_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS resolution_notes TEXT,
ADD COLUMN IF NOT EXISTS resolution_category TEXT,

-- Add flexible storage for additional context
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- ============================================================================
-- Create Indexes for Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_support_tickets_source_type 
  ON support_tickets(source_type);

CREATE INDEX IF NOT EXISTS idx_support_tickets_source_reference 
  ON support_tickets(source_reference_id);

CREATE INDEX IF NOT EXISTS idx_support_tickets_escalation_category 
  ON support_tickets(escalation_category);

CREATE INDEX IF NOT EXISTS idx_support_tickets_priority_status 
  ON support_tickets(priority, status);

CREATE INDEX IF NOT EXISTS idx_support_tickets_sentiment 
  ON support_tickets(bot_detected_sentiment);

CREATE INDEX IF NOT EXISTS idx_support_tickets_journey_stage 
  ON support_tickets(customer_journey_stage);

-- ============================================================================
-- Add Foreign Key Constraint to chat_sessions
-- ============================================================================

-- Link WhatsApp escalations to chat sessions
ALTER TABLE support_tickets 
ADD CONSTRAINT IF NOT EXISTS fk_support_tickets_chat_session 
FOREIGN KEY (source_reference_id) 
REFERENCES chat_sessions(id) 
ON DELETE SET NULL;

-- ============================================================================
-- Add Comments for Documentation
-- ============================================================================

COMMENT ON COLUMN support_tickets.source_type IS 
  'Source channel of the support ticket: whatsapp, web, email, chat, phone';

COMMENT ON COLUMN support_tickets.source_reference_id IS 
  'Reference ID from source system (e.g., chat_session_id for WhatsApp)';

COMMENT ON COLUMN support_tickets.source_phone_number IS 
  'Phone number for WhatsApp escalations (e.g., 256700123456)';

COMMENT ON COLUMN support_tickets.escalation_reason IS 
  'Detailed explanation of why escalation was needed';

COMMENT ON COLUMN support_tickets.escalation_category IS 
  'Category of the escalation for analytics and routing';

COMMENT ON COLUMN support_tickets.bot_detected_sentiment IS 
  'Customer sentiment detected by the bot (angry, negative, neutral, positive, confused)';

COMMENT ON COLUMN support_tickets.customer_journey_stage IS 
  'Stage of customer journey when escalation occurred';

COMMENT ON COLUMN support_tickets.first_response_at IS 
  'Timestamp when human agent first responded to ticket';

COMMENT ON COLUMN support_tickets.resolution_notes IS 
  'Internal notes about how the issue was resolved';

COMMENT ON COLUMN support_tickets.resolution_category IS 
  'Category of resolution for analytics';

COMMENT ON COLUMN support_tickets.metadata IS 
  'Flexible JSONB field for conversation context, bot confidence, keywords, etc.';

-- ============================================================================
-- Example Usage
-- ============================================================================
--
-- When bot escalates from WhatsApp:
-- 
-- INSERT INTO support_tickets (
--   customer_id,
--   source_type,
--   source_reference_id,
--   source_phone_number,
--   subject,
--   escalation_reason,
--   escalation_category,
--   priority,
--   status,
--   bot_detected_sentiment,
--   customer_journey_stage,
--   metadata
-- ) VALUES (
--   'customer-uuid',
--   'whatsapp',
--   'chat-session-uuid',
--   '256700123456',
--   'Customer requesting refund for damaged item',
--   'Customer received broken product and is upset, requesting immediate refund',
--   'refund_request',
--   'high',
--   'open',
--   'angry',
--   'delivery',
--   '{
--     "order_id": "order-uuid",
--     "conversation_summary": "Customer ordered iPhone...",
--     "keywords_detected": ["broken", "refund", "manager"],
--     "bot_confidence": 0.95
--   }'::jsonb
-- );
--
-- ============================================================================
-- Analytics Queries
-- ============================================================================
--
-- Most common escalation categories:
-- SELECT escalation_category, COUNT(*) as count
-- FROM support_tickets
-- WHERE source_type = 'whatsapp'
-- GROUP BY escalation_category
-- ORDER BY count DESC;
--
-- Average response time by priority:
-- SELECT priority, 
--   AVG(EXTRACT(EPOCH FROM (first_response_at - created_at))/60) as avg_minutes
-- FROM support_tickets
-- WHERE first_response_at IS NOT NULL
-- GROUP BY priority;
--
-- Sentiment distribution:
-- SELECT bot_detected_sentiment, COUNT(*) as count
-- FROM support_tickets
-- WHERE source_type = 'whatsapp'
-- GROUP BY bot_detected_sentiment;
--
-- ============================================================================
