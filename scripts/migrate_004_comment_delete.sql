-- L-Lawliet migration 004: deleting community notes.
-- Run in the Neon SQL Editor as the owner role (neondb_owner), after migration 003.
-- Safe to run more than once, and safe before or after deploying the code:
-- without this policy, RLS simply refuses every comment delete.
--
-- Rule: you can delete your own notes; an admin can delete any note (moderation).
-- lawliet_app already has DELETE on comments from grants.sql.

BEGIN;

DROP POLICY IF EXISTS comments_delete_own ON comments;
CREATE POLICY comments_delete_own ON comments FOR DELETE TO lawliet_app
    USING (user_id = app_user_id() OR app_role() = 'admin');

COMMIT;

-- Check (for a screenshot): the comments table now has four policies.
SELECT policyname, cmd FROM pg_policies WHERE tablename = 'comments' ORDER BY policyname;
