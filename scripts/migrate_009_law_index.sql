-- L-Lawliet migration 009: the full list of Philippine statutes.
-- Run once as the owner role (neondb_owner), BEFORE deploying the code that uses it, then
-- load the rows with:  python scripts/load_law_index.py
-- It only adds things, so the live code keeps working. Safe to re-run.
--
-- law_index lists every Act, Commonwealth Act, Republic Act, Presidential Decree and
-- Batas Pambansa: number, date, official title and a link to the full text. The `laws`
-- table keeps the hand-written plain-English cards; law_id links a listed law to its card.

BEGIN;

CREATE TABLE IF NOT EXISTS law_index (
    id              SERIAL       PRIMARY KEY,
    law_type        VARCHAR(4)   NOT NULL CHECK (law_type IN ('act', 'ca', 'ra', 'pd', 'bp')),
    number          VARCHAR(20)  NOT NULL CHECK (char_length(number) >= 1),
    label           VARCHAR(60)  NOT NULL,           -- "Republic Act No. 10175"
    enacted_on      DATE,                            -- NULL when the source date is unreadable
    year            SMALLINT     NOT NULL CHECK (year BETWEEN 1890 AND 2100),
    official_title  TEXT         NOT NULL CHECK (char_length(official_title) >= 3),
    source_url      VARCHAR(500) NOT NULL CHECK (source_url LIKE 'https://%'),
    law_id          INTEGER      REFERENCES laws(id) ON DELETE SET NULL,
    common_name     VARCHAR(520),                    -- the guide's titles, e.g. "Data Privacy Act of 2012"
    search          TSVECTOR     GENERATED ALWAYS AS (to_tsvector('english',
                        label || ' ' || coalesce(common_name, '') || ' ' || official_title)) STORED,
    UNIQUE (law_type, number)
);
CREATE INDEX IF NOT EXISTS idx_law_index_search ON law_index USING GIN (search);
CREATE INDEX IF NOT EXISTS idx_law_index_year   ON law_index (year DESC, law_type);
CREATE INDEX IF NOT EXISTS idx_law_index_law    ON law_index (law_id);

-- The list is public reference data: the API only reads it. Loading is done by the owner.
GRANT SELECT ON law_index TO lawliet_app;

ALTER TABLE law_index ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS law_index_read ON law_index;
CREATE POLICY law_index_read ON law_index FOR SELECT TO lawliet_app USING (true);

COMMIT;

-- Check (for a screenshot): the table, its RLS flag and its row count by type.
SELECT tablename, rowsecurity FROM pg_tables WHERE tablename = 'law_index';
SELECT law_type, COUNT(*) FROM law_index GROUP BY law_type ORDER BY law_type;
