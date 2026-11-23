-- L-Lawliet migration 007: game data for JustGiveupATP (JurisCards Arena).
-- The game has no database of its own. It reads laws and signs people in through this
-- API, and keeps each player's results and game settings in the two tables below.
--
-- Run once in the Neon SQL Editor as the owner role (neondb_owner), BEFORE deploying the
-- API code that uses these tables. It only adds tables. Safe to run more than once.
--
--   arena_results  one row per finished trial (won or lost)
--   arena_prefs    per-player game settings
--
-- Results are readable by everyone because the leaderboard is public; only the player
-- can add or clear their own. Deleting an account deletes its results and settings.

BEGIN;

CREATE TABLE IF NOT EXISTS arena_results (
    id        SERIAL PRIMARY KEY,
    user_id   INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    case_id   VARCHAR(60) NOT NULL CHECK (case_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    tier      SMALLINT    NOT NULL CHECK (tier BETWEEN 1 AND 3),
    won       BOOLEAN     NOT NULL,
    turns     SMALLINT    NOT NULL CHECK (turns BETWEEN 0 AND 500),
    jp_left   SMALLINT    NOT NULL CHECK (jp_left BETWEEN 0 AND 1000),
    played_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS arena_prefs (
    user_id         INTEGER     PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    confirm_abandon BOOLEAN     NOT NULL DEFAULT true,
    reduce_motion   BOOLEAN     NOT NULL DEFAULT false,
    hide_won        BOOLEAN     NOT NULL DEFAULT false,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_arena_results_user ON arena_results (user_id, played_at DESC);
CREATE INDEX IF NOT EXISTS idx_arena_results_case ON arena_results (case_id);

-- ---------- What the API role may do ----------
-- Results are never edited after they are saved, only added or cleared.
GRANT SELECT, INSERT, DELETE ON arena_results TO lawliet_app;
GRANT USAGE, SELECT ON SEQUENCE arena_results_id_seq TO lawliet_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON arena_prefs TO lawliet_app;

-- ---------- Row-Level Security ----------
-- app_user_id() and app_role() come from migration 003.
ALTER TABLE arena_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE arena_prefs   ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS arena_results_read   ON arena_results;
DROP POLICY IF EXISTS arena_results_insert ON arena_results;
DROP POLICY IF EXISTS arena_results_delete ON arena_results;
CREATE POLICY arena_results_read   ON arena_results FOR SELECT TO lawliet_app USING (true);
CREATE POLICY arena_results_insert ON arena_results FOR INSERT TO lawliet_app
    WITH CHECK (user_id = app_user_id());
CREATE POLICY arena_results_delete ON arena_results FOR DELETE TO lawliet_app
    USING (user_id = app_user_id());

DROP POLICY IF EXISTS arena_prefs_read  ON arena_prefs;
DROP POLICY IF EXISTS arena_prefs_write ON arena_prefs;
CREATE POLICY arena_prefs_read  ON arena_prefs FOR SELECT TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');
CREATE POLICY arena_prefs_write ON arena_prefs FOR ALL TO lawliet_app
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id());

COMMIT;

-- Check: both tables exist with RLS on.
SELECT tablename, rowsecurity FROM pg_tables
WHERE tablename IN ('arena_results', 'arena_prefs') ORDER BY tablename;
