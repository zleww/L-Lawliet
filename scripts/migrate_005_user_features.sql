-- L-Lawliet migration 005: saved laws, ratings, helpful votes, note reports, law suggestions,
-- and admin management of other accounts.
-- Run in the Neon SQL Editor as the owner role (neondb_owner) BEFORE deploying the code that
-- uses it (the new code reads these tables on every law page). It only adds things, so the
-- code that is live now keeps working after it runs. Safe to run more than once.

BEGIN;

-- ---------- New tables ----------

-- A user's bookmarks: many-to-many between users and laws.
CREATE TABLE IF NOT EXISTS saved_laws (
    user_id  INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    law_id   INTEGER     NOT NULL REFERENCES laws(id)  ON DELETE CASCADE,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, law_id)                 -- a law can be saved once per user
);
CREATE INDEX IF NOT EXISTS idx_saved_laws_law_id ON saved_laws (law_id);

-- One 1-to-5 rating per user per law; rating again changes it.
CREATE TABLE IF NOT EXISTS law_ratings (
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    law_id     INTEGER     NOT NULL REFERENCES laws(id)  ON DELETE CASCADE,
    rating     SMALLINT    NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, law_id)
);
CREATE INDEX IF NOT EXISTS idx_law_ratings_law_id ON law_ratings (law_id);

-- "Helpful" votes on notes: one per user per note.
CREATE TABLE IF NOT EXISTS comment_votes (
    user_id    INTEGER     NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    comment_id INTEGER     NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, comment_id)
);
CREATE INDEX IF NOT EXISTS idx_comment_votes_comment_id ON comment_votes (comment_id);

-- Reports on notes for the admins to review. Deleting the note removes its reports.
CREATE TABLE IF NOT EXISTS comment_reports (
    id          SERIAL PRIMARY KEY,
    comment_id  INTEGER      NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
    reporter_id INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    reason      VARCHAR(20)  NOT NULL CHECK (reason IN ('spam', 'offensive', 'wrong_info', 'other')),
    details     VARCHAR(500),
    status      VARCHAR(10)  NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'dismissed')),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    resolved_by INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS comment_reports_once_per_user ON comment_reports (comment_id, reporter_id);
CREATE INDEX IF NOT EXISTS idx_comment_reports_status ON comment_reports (status);

-- Laws users ask the admins to add. An approved suggestion points at the law created for it.
CREATE TABLE IF NOT EXISTS law_suggestions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER       REFERENCES users(id) ON DELETE SET NULL,
    ra_number   VARCHAR(20)   NOT NULL CHECK (char_length(ra_number) >= 3),
    title       VARCHAR(200)  NOT NULL CHECK (char_length(title) >= 3),
    reason      VARCHAR(1000) NOT NULL CHECK (char_length(reason) >= 10),
    source_url  VARCHAR(500)  CHECK (source_url IS NULL OR source_url LIKE 'https://%'),
    status      VARCHAR(10)   NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    admin_note  VARCHAR(500),
    reviewed_by INTEGER       REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    law_id      INTEGER       REFERENCES laws(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);
-- One open suggestion per user per RA number.
CREATE UNIQUE INDEX IF NOT EXISTS law_suggestions_one_pending
    ON law_suggestions (user_id, ra_number) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_law_suggestions_status ON law_suggestions (status);

-- ---------- Privileges for the API role (least privilege, column-level updates) ----------
GRANT SELECT, INSERT, DELETE ON saved_laws, comment_votes TO lawliet_app;
GRANT SELECT, INSERT, DELETE ON law_ratings TO lawliet_app;
GRANT UPDATE (rating, updated_at) ON law_ratings TO lawliet_app;
GRANT SELECT, INSERT ON comment_reports, law_suggestions TO lawliet_app;
GRANT UPDATE (status, resolved_by, resolved_at) ON comment_reports TO lawliet_app;
GRANT UPDATE (status, admin_note, reviewed_by, reviewed_at, law_id) ON law_suggestions TO lawliet_app;
GRANT USAGE, SELECT ON SEQUENCE comment_reports_id_seq, law_suggestions_id_seq TO lawliet_app;

-- ---------- Row-Level Security ----------
ALTER TABLE saved_laws      ENABLE ROW LEVEL SECURITY;
ALTER TABLE law_ratings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE comment_votes   ENABLE ROW LEVEL SECURITY;
ALTER TABLE comment_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE law_suggestions ENABLE ROW LEVEL SECURITY;

-- saved_laws: private to their owner.
DROP POLICY IF EXISTS saved_laws_own ON saved_laws;
CREATE POLICY saved_laws_own ON saved_laws FOR ALL TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

-- law_ratings and comment_votes: everyone may read (averages and counts); write only your own.
DROP POLICY IF EXISTS law_ratings_read  ON law_ratings;
DROP POLICY IF EXISTS law_ratings_write ON law_ratings;
CREATE POLICY law_ratings_read  ON law_ratings FOR SELECT TO lawliet_app USING (true);
CREATE POLICY law_ratings_write ON law_ratings FOR ALL    TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

DROP POLICY IF EXISTS comment_votes_read  ON comment_votes;
DROP POLICY IF EXISTS comment_votes_write ON comment_votes;
CREATE POLICY comment_votes_read  ON comment_votes FOR SELECT TO lawliet_app USING (true);
CREATE POLICY comment_votes_write ON comment_votes FOR ALL    TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

-- comment_reports: you file reports as yourself and see your own; admins see and resolve all.
DROP POLICY IF EXISTS comment_reports_insert ON comment_reports;
DROP POLICY IF EXISTS comment_reports_read   ON comment_reports;
DROP POLICY IF EXISTS comment_reports_admin  ON comment_reports;
CREATE POLICY comment_reports_insert ON comment_reports FOR INSERT TO lawliet_app
    WITH CHECK (reporter_id = app_user_id() AND status = 'open');
CREATE POLICY comment_reports_read   ON comment_reports FOR SELECT TO lawliet_app
    USING (reporter_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY comment_reports_admin  ON comment_reports FOR UPDATE TO lawliet_app
    USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');

-- law_suggestions: you submit as yourself (always pending) and see your own; admins review all.
DROP POLICY IF EXISTS law_suggestions_insert ON law_suggestions;
DROP POLICY IF EXISTS law_suggestions_read   ON law_suggestions;
DROP POLICY IF EXISTS law_suggestions_admin  ON law_suggestions;
CREATE POLICY law_suggestions_insert ON law_suggestions FOR INSERT TO lawliet_app
    WITH CHECK (user_id = app_user_id() AND status = 'pending');
CREATE POLICY law_suggestions_read   ON law_suggestions FOR SELECT TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY law_suggestions_admin  ON law_suggestions FOR UPDATE TO lawliet_app
    USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');

-- ---------- Admin management of other accounts ----------
-- Admins may unlock an account or sign it out everywhere (only the columns granted in 003:
-- never role or username), and delete accounts that are not admins.
DROP POLICY IF EXISTS users_admin_update ON users;
DROP POLICY IF EXISTS users_admin_delete ON users;
CREATE POLICY users_admin_update ON users FOR UPDATE TO lawliet_app
    USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');
CREATE POLICY users_admin_delete ON users FOR DELETE TO lawliet_app
    USING (app_role() = 'admin' AND role <> 'admin');

-- When an admin deletes an account, that account's notes are renamed "Deleted user".
DROP POLICY IF EXISTS comments_admin_update ON comments;
CREATE POLICY comments_admin_update ON comments FOR UPDATE TO lawliet_app
    USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');

COMMIT;

-- Check (for a screenshot): the new tables have RLS on and their policies exist.
SELECT tablename, rowsecurity FROM pg_tables
WHERE tablename IN ('saved_laws', 'law_ratings', 'comment_votes', 'comment_reports', 'law_suggestions')
ORDER BY tablename;
SELECT tablename, policyname, cmd FROM pg_policies
WHERE tablename IN ('saved_laws', 'law_ratings', 'comment_votes', 'comment_reports', 'law_suggestions', 'users', 'comments')
ORDER BY tablename, policyname;
