-- ============================================================================
-- Customer Feedback Table
-- ============================================================================
-- Separate from support_tickets - this is for collecting customer opinions,
-- ratings, suggestions, and satisfaction data (not problems/escalations)
-- ============================================================================

CREATE TABLE IF NOT EXISTS customer_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Who & Where
  customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  source_type TEXT CHECK (source_type IN ('whatsapp', 'web', 'email', 'sms', 'post_delivery')) DEFAULT 'whatsapp',
  source_reference_id UUID, -- chat_session_id or order_id
  
  -- What type of feedback
  feedback_type TEXT CHECK (feedback_type IN (
    'general', 
    'order_experience', 
    'delivery_experience', 
    'product_quality',
    'customer_service',
    'app_usability',
    'suggestion',
    'complaint'
  )) NOT NULL,
  
  -- Rating (optional - 1 to 5 stars)
  rating INTEGER CHECK (rating >= 1 AND rating <= 5),
  
  -- Feedback content
  feedback_text TEXT NOT NULL,
  sentiment TEXT CHECK (sentiment IN ('positive', 'neutral', 'negative')), -- Bot-detected
  
  -- Context
  order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
  related_agent_id UUID REFERENCES profiles(id) ON DELETE SET NULL, -- If feedback about specific agent
  journey_stage TEXT CHECK (journey_stage IN ('quotation', 'cart', 'payment', 'delivery', 'post_delivery', 'other')),
  
  -- Follow-up tracking
  requires_follow_up BOOLEAN DEFAULT FALSE,
  followed_up_at TIMESTAMPTZ,
  follow_up_notes TEXT,
  
  -- Flexible storage
  metadata JSONB DEFAULT '{}'::jsonb,
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

CREATE INDEX idx_customer_feedback_customer ON customer_feedback(customer_id);
CREATE INDEX idx_customer_feedback_type ON customer_feedback(feedback_type);
CREATE INDEX idx_customer_feedback_rating ON customer_feedback(rating);
CREATE INDEX idx_customer_feedback_sentiment ON customer_feedback(sentiment);
CREATE INDEX idx_customer_feedback_requires_follow_up ON customer_feedback(requires_follow_up) WHERE requires_follow_up = TRUE;
CREATE INDEX idx_customer_feedback_created_at ON customer_feedback(created_at DESC);
CREATE INDEX idx_customer_feedback_order ON customer_feedback(order_id) WHERE order_id IS NOT NULL;
CREATE INDEX idx_customer_feedback_source ON customer_feedback(source_type, source_reference_id);

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE customer_feedback IS 'Customer feedback from all sources - ratings, suggestions, satisfaction surveys';
COMMENT ON COLUMN customer_feedback.sentiment IS 'Bot-detected sentiment from feedback text';
COMMENT ON COLUMN customer_feedback.requires_follow_up IS 'TRUE if feedback needs management response or action';
COMMENT ON COLUMN customer_feedback.rating IS 'Optional 1-5 star rating';
COMMENT ON COLUMN customer_feedback.metadata IS 'Additional context: keywords, triggers, bot_confidence, etc.';

-- ============================================================================
-- Auto-update timestamp trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION update_customer_feedback_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_customer_feedback_updated_at
  BEFORE UPDATE ON customer_feedback
  FOR EACH ROW
  EXECUTE FUNCTION update_customer_feedback_updated_at();

-- ============================================================================
-- Row Level Security
-- ============================================================================

ALTER TABLE customer_feedback ENABLE ROW LEVEL SECURITY;

-- Customers can view their own feedback
CREATE POLICY customers_view_own_feedback ON customer_feedback
  FOR SELECT
  USING (
    auth.uid() IN (
      SELECT profile_id FROM customers WHERE id = customer_feedback.customer_id
    )
  );

-- Service role can do everything
CREATE POLICY service_all_feedback ON customer_feedback
  FOR ALL
  USING (auth.role() = 'service_role');

-- ============================================================================
-- Analytics View
-- ============================================================================

CREATE OR REPLACE VIEW feedback_analytics AS
SELECT 
  DATE_TRUNC('day', created_at) as date,
  feedback_type,
  sentiment,
  COUNT(*) as count,
  AVG(rating) as avg_rating,
  COUNT(CASE WHEN requires_follow_up THEN 1 END) as needs_follow_up
FROM customer_feedback
WHERE created_at >= NOW() - INTERVAL '90 days'
GROUP BY DATE_TRUNC('day', created_at), feedback_type, sentiment;

COMMENT ON VIEW feedback_analytics IS 'Daily feedback metrics for analytics dashboard';
