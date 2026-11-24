-- L-Lawliet migration 008: forgot password and recovery email.
-- Run once in the Neon SQL Editor as the owner role (neondb_owner), BEFORE deploying the
-- code that uses it. It only adds things, so the live code keeps working. Safe to re-run.
--
-- account_tokens holds one row per emailed link (confirm an email, or reset a password).
-- Only the SHA-256 hash of the link's token is stored, so even a full copy of the
-- database cannot be turned into working links. Each link works once and expires.

BEGIN;

CREATE TABLE IF NOT EXISTS account_tokens (
    id          SERIAL       PRIMARY KEY,
    user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose     VARCHAR(20)  NOT NULL CHECK (purpose IN ('reset_password', 'verify_email')),
    email       VARCHAR(254) NOT NULL,          -- where the link was sent
    token_hash  CHAR(64)     NOT NULL UNIQUE,   -- sha256 hex of the token in the link
    expires_at  TIMESTAMPTZ  NOT NULL,
    used_at     TIMESTAMPTZ,                    -- NULL = not used yet
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_account_tokens_user ON account_tokens (user_id, purpose, created_at);

-- lawliet_app may read and create links and mark them used; never change a hash or expiry.
GRANT SELECT, INSERT ON account_tokens TO lawliet_app;
GRANT UPDATE (used_at) ON account_tokens TO lawliet_app;
GRANT USAGE, SELECT ON SEQUENCE account_tokens_id_seq TO lawliet_app;

-- users.email: migration 003 kept it read-only. A username account may now set it, but the
-- API only does so after the owner opens the confirmation link. Role, username and
-- google_sub stay read-only.
GRANT UPDATE (email) ON users TO lawliet_app;

-- Row-Level Security: a link is looked up by its hash before anyone is logged in, so rows
-- are readable; creating or using a link only works while acting as that account.
ALTER TABLE account_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_tokens_read       ON account_tokens;
DROP POLICY IF EXISTS account_tokens_insert_own ON account_tokens;
DROP POLICY IF EXISTS account_tokens_update_own ON account_tokens;
CREATE POLICY account_tokens_read       ON account_tokens FOR SELECT TO lawliet_app USING (true);
CREATE POLICY account_tokens_insert_own ON account_tokens FOR INSERT TO lawliet_app
    WITH CHECK (user_id = app_user_id());
CREATE POLICY account_tokens_update_own ON account_tokens FOR UPDATE TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

COMMIT;

-- Check (for a screenshot): the table, its RLS flag and its policies.
SELECT tablename, rowsecurity FROM pg_tables WHERE tablename = 'account_tokens';
SELECT policyname, cmd FROM pg_policies WHERE tablename = 'account_tokens' ORDER BY policyname;
