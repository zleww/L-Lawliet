-- L-Lawliet migration 010: every listed law becomes a law people can save, rate and comment on.
-- Run as the owner role (neondb_owner) AFTER migration 009 and its loader, in two parts:
--   PART A (schema only) BEFORE deploying the code: the old code keeps working, since every
--          existing row stays a guide.
--   PART B (adds the listed laws) AFTER the new code is live: the old code would list them all.
-- Both parts are safe to re-run.
--
-- Each of the ~19,600 laws in law_index gets a row in `laws` with has_guide = false: just its
-- number, title, year and full-text link. Saves, ratings, notes, votes and reports already hang
-- off laws(id), so they work for every law. The plain-English fields stay required for guides
-- (has_guide = true), and every list that shows guides (GET /laws, stats, study, the partner
-- sites) filters on has_guide, so those lists do not change.

-- ===================== PART A =====================
BEGIN;

ALTER TABLE laws ADD COLUMN IF NOT EXISTS has_guide BOOLEAN NOT NULL DEFAULT true;

-- Listed titles can be long (up to ~1,700 characters); guides keep the 300 limit in the API.
ALTER TABLE laws ALTER COLUMN official_title TYPE TEXT;

ALTER TABLE laws
    ALTER COLUMN plain_title          DROP NOT NULL,
    ALTER COLUMN category             DROP NOT NULL,
    ALTER COLUMN status               DROP NOT NULL,
    ALTER COLUMN reading_time_minutes DROP NOT NULL,
    ALTER COLUMN importance_rating    DROP NOT NULL,
    ALTER COLUMN tldr_summary         DROP NOT NULL,
    ALTER COLUMN full_breakdown       DROP NOT NULL,
    ALTER COLUMN why_it_matters       DROP NOT NULL,
    ALTER COLUMN example_scenario     DROP NOT NULL,
    ALTER COLUMN penalties            DROP NOT NULL,
    ALTER COLUMN min_fine_php         DROP NOT NULL,
    ALTER COLUMN total_sections       DROP NOT NULL,
    ALTER COLUMN enacting_president   DROP NOT NULL,
    ALTER COLUMN target_audience      DROP NOT NULL;

-- A guide must still have every plain-English field.
ALTER TABLE laws DROP CONSTRAINT IF EXISTS laws_guide_complete;
ALTER TABLE laws ADD CONSTRAINT laws_guide_complete CHECK (NOT has_guide OR (
    plain_title IS NOT NULL AND category IS NOT NULL AND status IS NOT NULL
    AND reading_time_minutes IS NOT NULL AND importance_rating IS NOT NULL
    AND tldr_summary IS NOT NULL AND full_breakdown IS NOT NULL AND why_it_matters IS NOT NULL
    AND example_scenario IS NOT NULL AND penalties IS NOT NULL AND min_fine_php IS NOT NULL
    AND total_sections IS NOT NULL AND enacting_president IS NOT NULL AND target_audience IS NOT NULL
));

CREATE INDEX IF NOT EXISTS idx_laws_has_guide ON laws (has_guide, id);

COMMIT;

-- ===================== PART B =====================
BEGIN;

-- One law row per listed law that has no guide yet. Numbers follow the guides' style:
-- "RA 10175", "PD 1606", "BP 22", "CA 733", "Act 3815".
INSERT INTO laws (ra_number, official_title, year, source_url, status, has_guide)
SELECT CASE i.law_type WHEN 'ra' THEN 'RA ' WHEN 'pd' THEN 'PD ' WHEN 'bp' THEN 'BP '
                       WHEN 'ca' THEN 'CA ' ELSE 'Act ' END || i.number,
       i.official_title, GREATEST(i.year, 1900), i.source_url, NULL, false
FROM law_index i
WHERE i.law_id IS NULL
ON CONFLICT (ra_number) DO NOTHING;

UPDATE law_index i SET law_id = l.id
FROM laws l
WHERE i.law_id IS NULL
  AND l.ra_number = CASE i.law_type WHEN 'ra' THEN 'RA ' WHEN 'pd' THEN 'PD ' WHEN 'bp' THEN 'BP '
                                    WHEN 'ca' THEN 'CA ' ELSE 'Act ' END || i.number;

COMMIT;

-- Check (for a screenshot): guides vs listed laws, and that every listed law is linked.
SELECT has_guide, COUNT(*) FROM laws GROUP BY has_guide;
SELECT COUNT(*) AS unlinked FROM law_index WHERE law_id IS NULL;
