-- L-Lawliet migration 003: database security rules (column privileges + Row-Level Security).
-- Run in the Neon SQL Editor as the owner role (neondb_owner) AFTER the new API code is
-- deployed. The old code does not tell the database who is acting, so these rules would
-- block its writes. Safe to run more than once.
--
-- How it works: on every write, the API runs
--     SELECT set_config('app.user_id', '<id>', true), set_config('app.role', '<role>', true)
-- inside the same transaction, using the id and role it loaded from the database for
-- the verified login token. The policies below read those two values, so even if an API
-- route forgot a check, PostgreSQL itself refuses the change.
--
-- These rules apply to lawliet_app only. The owner role bypasses RLS (it owns the
-- tables), which is why seed.py and the SQL Editor still work. RLS would also be
-- bypassed by a role with BYPASSRLS, which is one more reason lawliet_app is not in
-- neon_superuser.

BEGIN;

-- ---------- Who is acting (empty or missing = nobody / guest) ----------
CREATE OR REPLACE FUNCTION app_user_id() RETURNS integer
    LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::integer $$;

CREATE OR REPLACE FUNCTION app_role() RETURNS text
    LANGUAGE sql STABLE AS $$ SELECT COALESCE(NULLIF(current_setting('app.role', true), ''), 'guest') $$;

-- ---------- Column privileges: what lawliet_app may change at all ----------
-- users: never role, username, email or google_sub after the account exists
-- (no one can promote themselves to admin through the API, even with a bug).
REVOKE UPDATE ON users FROM lawliet_app;
GRANT UPDATE (display_name, bio, theme, accent, password_hash, token_version,
              failed_logins, locked_until, updated_at) ON users TO lawliet_app;

-- comments: only the text, the shown name and the edit time; never law_id or user_id.
REVOKE UPDATE ON comments FROM lawliet_app;
GRANT UPDATE (comment, user_name, updated_at) ON comments TO lawliet_app;

-- ---------- Row-Level Security ----------
ALTER TABLE laws     ENABLE ROW LEVEL SECURITY;
ALTER TABLE comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE users    ENABLE ROW LEVEL SECURITY;

-- laws: everyone reads (the guest 10-law limit stays in the API query); only admins write.
DROP POLICY IF EXISTS laws_read         ON laws;
DROP POLICY IF EXISTS laws_admin_insert ON laws;
DROP POLICY IF EXISTS laws_admin_update ON laws;
DROP POLICY IF EXISTS laws_admin_delete ON laws;
CREATE POLICY laws_read         ON laws FOR SELECT TO lawliet_app USING (true);
CREATE POLICY laws_admin_insert ON laws FOR INSERT TO lawliet_app WITH CHECK (app_role() = 'admin');
CREATE POLICY laws_admin_update ON laws FOR UPDATE TO lawliet_app
    USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY laws_admin_delete ON laws FOR DELETE TO lawliet_app USING (app_role() = 'admin');

-- comments: everyone reads; you can only post as yourself and only edit your own.
-- (Deleting a law still removes its comments: foreign-key cascades bypass RLS.)
DROP POLICY IF EXISTS comments_read       ON comments;
DROP POLICY IF EXISTS comments_insert_own ON comments;
DROP POLICY IF EXISTS comments_update_own ON comments;
CREATE POLICY comments_read       ON comments FOR SELECT TO lawliet_app USING (true);
CREATE POLICY comments_insert_own ON comments FOR INSERT TO lawliet_app
    WITH CHECK (user_id = app_user_id());
CREATE POLICY comments_update_own ON comments FOR UPDATE TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

-- users: rows are readable (login has to find the account before anyone is known;
-- the API never sends password_hash to a browser). New accounts can only be ordinary
-- users. You can only change or delete your own account.
DROP POLICY IF EXISTS users_read        ON users;
DROP POLICY IF EXISTS users_signup      ON users;
DROP POLICY IF EXISTS users_update_self ON users;
DROP POLICY IF EXISTS users_delete_self ON users;
CREATE POLICY users_read        ON users FOR SELECT TO lawliet_app USING (true);
CREATE POLICY users_signup      ON users FOR INSERT TO lawliet_app WITH CHECK (role = 'user');
CREATE POLICY users_update_self ON users FOR UPDATE TO lawliet_app
    USING (id = app_user_id()) WITH CHECK (id = app_user_id());
CREATE POLICY users_delete_self ON users FOR DELETE TO lawliet_app USING (id = app_user_id());

COMMIT;

-- Check (for a screenshot): RLS is on and the policies exist.
SELECT tablename, rowsecurity FROM pg_tables WHERE tablename IN ('laws', 'comments', 'users');
SELECT tablename, policyname, cmd, roles FROM pg_policies ORDER BY tablename, policyname;
