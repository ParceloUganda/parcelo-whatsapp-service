-- ============================================================================
-- Magic Authentication Tokens Table
-- ============================================================================
-- This table stores secure tokens for WhatsApp magic link authentication.
-- When a WhatsApp user wants to access the website, they receive a magic link
-- that contains a token. This token is stored here and validated when clicked.
-- ============================================================================

-- Create the magic_auth_tokens table
CREATE TABLE IF NOT EXISTS magic_auth_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token TEXT UNIQUE NOT NULL,
  phone_number TEXT NOT NULL,
  customer_id UUID REFERENCES customers(id),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Constraints
  CONSTRAINT token_not_empty CHECK (length(token) > 0),
  CONSTRAINT phone_not_empty CHECK (length(phone_number) > 0),
  CONSTRAINT expires_after_creation CHECK (expires_at > created_at)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_magic_tokens_token ON magic_auth_tokens(token);
CREATE INDEX IF NOT EXISTS idx_magic_tokens_phone ON magic_auth_tokens(phone_number);
CREATE INDEX IF NOT EXISTS idx_magic_tokens_expires ON magic_auth_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_magic_tokens_customer ON magic_auth_tokens(customer_id);

-- Add comments for documentation
COMMENT ON TABLE magic_auth_tokens IS 'Stores magic link tokens for WhatsApp authentication';
COMMENT ON COLUMN magic_auth_tokens.token IS 'Secure 64-character random hex token';
COMMENT ON COLUMN magic_auth_tokens.phone_number IS 'Customer phone number (e.g., 256700123456)';
COMMENT ON COLUMN magic_auth_tokens.customer_id IS 'Reference to customers table';
COMMENT ON COLUMN magic_auth_tokens.expires_at IS 'Token expiration timestamp (typically 1 hour from creation)';
COMMENT ON COLUMN magic_auth_tokens.used_at IS 'Timestamp when token was used (NULL if not used)';

-- ============================================================================
-- Cleanup Function
-- ============================================================================
-- This function removes expired tokens to keep the table clean.
-- You can schedule this to run periodically (e.g., daily via cron).
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_expired_magic_tokens()
RETURNS void AS $$
BEGIN
  DELETE FROM magic_auth_tokens
  WHERE expires_at < NOW() - INTERVAL '24 hours';
  
  RAISE NOTICE 'Cleaned up expired magic tokens';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_magic_tokens() IS 'Removes expired magic tokens older than 24 hours';

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================
-- Restrict access to this table for security.
-- Only service role should be able to read/write these tokens.
-- ============================================================================

-- Enable RLS
ALTER TABLE magic_auth_tokens ENABLE ROW LEVEL SECURITY;

-- Policy: Only service role can read tokens
CREATE POLICY service_only_read_magic_tokens ON magic_auth_tokens
  FOR SELECT
  USING (auth.role() = 'service_role');

-- Policy: Only service role can insert tokens
CREATE POLICY service_only_insert_magic_tokens ON magic_auth_tokens
  FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

-- Policy: Only service role can update tokens (for marking as used)
CREATE POLICY service_only_update_magic_tokens ON magic_auth_tokens
  FOR UPDATE
  USING (auth.role() = 'service_role');

-- Policy: Only service role can delete tokens
CREATE POLICY service_only_delete_magic_tokens ON magic_auth_tokens
  FOR DELETE
  USING (auth.role() = 'service_role');

-- ============================================================================
-- Example Usage
-- ============================================================================
-- 
-- 1. Create a magic token (done by Next.js API):
-- INSERT INTO magic_auth_tokens (token, phone_number, customer_id, expires_at)
-- VALUES (
--   'abc123...64chars',
--   '256700123456',
--   'customer-uuid-here',
--   NOW() + INTERVAL '1 hour'
-- );
--
-- 2. Validate a token (done by Next.js API):
-- SELECT * FROM magic_auth_tokens
-- WHERE token = 'abc123...64chars'
--   AND expires_at > NOW()
--   AND used_at IS NULL;
--
-- 3. Mark token as used (done by Next.js API):
-- UPDATE magic_auth_tokens
-- SET used_at = NOW()
-- WHERE token = 'abc123...64chars';
--
-- 4. Cleanup old tokens (run periodically):
-- SELECT cleanup_expired_magic_tokens();
--
-- ============================================================================
