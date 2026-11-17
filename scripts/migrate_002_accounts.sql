-- L-Lawliet migration 002: accounts, Google sign-in, profiles and comment editing.
-- Run once in the Neon SQL Editor as the owner role (neondb_owner), BEFORE deploying
-- the code that uses these columns. It only adds things, so the code that is live
-- now keeps working after it runs.
-- Run order: schema.sql -> grants.sql -> seed.py -> 002 (this file) -> deploy -> 003.

BEGIN;

-- ---------- users: sign-up, Google sign-in, profile, sessions, lockout ----------
ALTER TABLE users
    ALTER COLUMN password_hash DROP NOT NULL,                 -- Google-only accounts have no password
    ADD COLUMN email         VARCHAR(254),                    -- from Google; verified by Google
    ADD COLUMN google_sub    VARCHAR(255),                    -- Google's stable account id
    ADD COLUMN display_name  VARCHAR(100) CHECK (char_length(display_name) >= 1),
    ADD COLUMN bio           VARCHAR(300),
    ADD COLUMN theme         VARCHAR(10)  NOT NULL DEFAULT 'dark' CHECK (theme IN ('dark', 'light')),
    ADD COLUMN accent        VARCHAR(10)  NOT NULL DEFAULT 'gold'
                                 CHECK (accent IN ('gold', 'blue', 'green', 'rose')),
    ADD COLUMN token_version INTEGER      NOT NULL DEFAULT 0, -- +1 = every old login token stops working
    ADD COLUMN failed_logins SMALLINT     NOT NULL DEFAULT 0,
    ADD COLUMN locked_until  TIMESTAMPTZ,
    ADD COLUMN updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ADD CONSTRAINT users_has_login CHECK (password_hash IS NOT NULL OR google_sub IS NOT NULL);

-- One account per Google account / email, and usernames unique regardless of case
-- ("Admin" and "admin" cannot both exist).
CREATE UNIQUE INDEX users_google_sub_key     ON users (google_sub) WHERE google_sub IS NOT NULL;
CREATE UNIQUE INDEX users_email_lower_key    ON users (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX users_username_lower_key ON users (lower(username));

-- ---------- comments: editing ----------
ALTER TABLE comments ADD COLUMN updated_at TIMESTAMPTZ;      -- NULL = never edited
CREATE INDEX idx_comments_user_id ON comments (user_id);

COMMIT;

-- Check: the new columns exist.
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name IN ('users', 'comments')
ORDER BY table_name, ordinal_position;
