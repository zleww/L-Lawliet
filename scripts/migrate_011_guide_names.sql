-- L-Lawliet migration 011: when an admin adds, edits or removes a guide, the API copies the
-- guide's titles into law_index.common_name, so the full list finds the law by its everyday
-- name ("Data Privacy Act"). Run once as the owner role BEFORE deploying that code. Safe to re-run.

BEGIN;

GRANT UPDATE (common_name) ON law_index TO lawliet_app;

DROP POLICY IF EXISTS law_index_admin_update ON law_index;
CREATE POLICY law_index_admin_update ON law_index FOR UPDATE TO lawliet_app
    USING (app_role() = 'admin') WITH CHECK (app_role() = 'admin');

COMMIT;

SELECT policyname, cmd FROM pg_policies WHERE tablename = 'law_index' ORDER BY policyname;
