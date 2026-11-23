-- L-Lawliet migration 006: study data for JurisCard.
-- JurisCard (juris-card.vercel.app) has no database of its own. It signs people in with
-- the same users table and reads the same laws table through this API, and keeps each
-- account's study data in the four tables below.
--
-- Run once in the Neon SQL Editor as the owner role (neondb_owner), BEFORE deploying the
-- API code that uses these tables. It only adds tables, so the live code keeps working.
-- Safe to run more than once.
--
--   flashcards     cards a user writes themselves
--   law_progress   how a user marked each law's card: 'review' or 'mastered'
--   quiz_attempts  one row per finished practice quiz
--   study_prefs    quiz length, daily goal and deck options
--
-- Deleting an account deletes its study data (ON DELETE CASCADE). Deleting a law deletes
-- the progress rows that point at it.

BEGIN;

CREATE TABLE IF NOT EXISTS flashcards (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category   VARCHAR(30)   NOT NULL CHECK (category IN (
                   'Technology & Crime', 'Finance & Taxes', 'Governance & Business',
                   'Social & Welfare', 'Environment', 'Education & Civil Rights')),
    question   VARCHAR(300)  NOT NULL CHECK (char_length(question) >= 5),
    answer     VARCHAR(1500) NOT NULL CHECK (char_length(answer) >= 2),
    source     VARCHAR(100),
    status     VARCHAR(10)   NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'review', 'mastered')),
    created_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS law_progress (
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    law_id     INTEGER     NOT NULL REFERENCES laws(id)  ON DELETE CASCADE,
    status     VARCHAR(10) NOT NULL CHECK (status IN ('review', 'mastered')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, law_id)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id       SERIAL PRIMARY KEY,
    user_id  INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(30),                       -- NULL = all categories
    score    SMALLINT    NOT NULL,
    total    SMALLINT    NOT NULL CHECK (total BETWEEN 1 AND 50),
    taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (score BETWEEN 0 AND total)
);

CREATE TABLE IF NOT EXISTS study_prefs (
    user_id       INTEGER     PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    quiz_length   SMALLINT    NOT NULL DEFAULT 10 CHECK (quiz_length IN (5, 10, 15, 20)),
    daily_goal    SMALLINT    NOT NULL DEFAULT 10 CHECK (daily_goal BETWEEN 1 AND 100),
    hide_mastered BOOLEAN     NOT NULL DEFAULT false,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_flashcards_user    ON flashcards (user_id);
CREATE INDEX IF NOT EXISTS idx_law_progress_law   ON law_progress (law_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user ON quiz_attempts (user_id, taken_at DESC);

-- ---------- What the API role may do ----------
GRANT SELECT, INSERT, UPDATE, DELETE ON flashcards, law_progress, quiz_attempts, study_prefs TO lawliet_app;
GRANT USAGE, SELECT ON SEQUENCE flashcards_id_seq, quiz_attempts_id_seq TO lawliet_app;
-- Quiz results are never edited after they are saved.
REVOKE UPDATE ON quiz_attempts FROM lawliet_app;
-- A card can never be moved to another account.
REVOKE UPDATE ON flashcards FROM lawliet_app;
GRANT UPDATE (category, question, answer, source, status, updated_at) ON flashcards TO lawliet_app;

-- ---------- Row-Level Security: your own rows only; admins may read everyone's ----------
-- app_user_id() and app_role() come from migration 003.
ALTER TABLE flashcards    ENABLE ROW LEVEL SECURITY;
ALTER TABLE law_progress  ENABLE ROW LEVEL SECURITY;
ALTER TABLE quiz_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE study_prefs   ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS flashcards_read  ON flashcards;
DROP POLICY IF EXISTS flashcards_write ON flashcards;
CREATE POLICY flashcards_read  ON flashcards FOR SELECT TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY flashcards_write ON flashcards FOR ALL TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

DROP POLICY IF EXISTS law_progress_read  ON law_progress;
DROP POLICY IF EXISTS law_progress_write ON law_progress;
CREATE POLICY law_progress_read  ON law_progress FOR SELECT TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY law_progress_write ON law_progress FOR ALL TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

DROP POLICY IF EXISTS quiz_attempts_read  ON quiz_attempts;
DROP POLICY IF EXISTS quiz_attempts_write ON quiz_attempts;
CREATE POLICY quiz_attempts_read  ON quiz_attempts FOR SELECT TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY quiz_attempts_write ON quiz_attempts FOR ALL TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

DROP POLICY IF EXISTS study_prefs_read  ON study_prefs;
DROP POLICY IF EXISTS study_prefs_write ON study_prefs;
CREATE POLICY study_prefs_read  ON study_prefs FOR SELECT TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY study_prefs_write ON study_prefs FOR ALL TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

COMMIT;

-- Check: the four tables exist with RLS on.
SELECT tablename, rowsecurity FROM pg_tables
WHERE tablename IN ('flashcards', 'law_progress', 'quiz_attempts', 'study_prefs')
ORDER BY tablename;
