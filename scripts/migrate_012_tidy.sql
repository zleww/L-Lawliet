-- L-Lawliet migration 012: database tidy-up. Run as the owner role (neondb_owner). Safe to re-run.
-- Nothing is deleted.

-- 1. Indexes on the four foreign keys that had none, so deleting a user or a law (which checks
--    these columns) and the admin lists that filter on them do not scan the whole table.
CREATE INDEX IF NOT EXISTS idx_comment_reports_reporter ON comment_reports (reporter_id);
CREATE INDEX IF NOT EXISTS idx_comment_reports_resolved_by ON comment_reports (resolved_by);
CREATE INDEX IF NOT EXISTS idx_law_suggestions_reviewed_by ON law_suggestions (reviewed_by);
CREATE INDEX IF NOT EXISTS idx_law_suggestions_law ON law_suggestions (law_id);

-- 2. The Part I test table republic_acts is kept, but locked: Row-Level Security on with no
--    policies, and no rights for the app role, so only the owner can read it.
ALTER TABLE republic_acts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON republic_acts FROM lawliet_app;
REVOKE ALL ON republic_acts FROM PUBLIC;

-- Check (for a screenshot)
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT indexname FROM pg_indexes WHERE indexname IN
  ('idx_comment_reports_reporter', 'idx_comment_reports_resolved_by',
   'idx_law_suggestions_reviewed_by', 'idx_law_suggestions_law');
