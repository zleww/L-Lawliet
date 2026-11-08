-- Least-privilege access for the API's own role.
-- Step 1: in the Neon console (Roles page), create a role named lawliet_app.
--         Neon generates its password; do not paste it anywhere public.
-- Step 2: run this file in the SQL Editor as the owner role, after schema.sql.
-- The API connects as lawliet_app: it can read and write rows in the three
-- tables, and nothing else (no DROP, ALTER or CREATE).

GRANT USAGE ON SCHEMA public TO lawliet_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON laws, comments, users TO lawliet_app;
GRANT USAGE, SELECT ON SEQUENCE laws_id_seq, comments_id_seq, users_id_seq TO lawliet_app;

-- Check what else lawliet_app inherits (for screenshot 4.2 / the security section).
-- If it lists neon_superuser, the role is broader than intended: record that as a
-- limitation, or recreate the role in SQL (CREATE ROLE lawliet_app LOGIN PASSWORD ...)
-- and re-run the GRANTs above.
SELECT r.rolname AS role, m.rolname AS member_of
FROM pg_roles r
LEFT JOIN pg_auth_members am ON am.member = r.oid
LEFT JOIN pg_roles m ON m.oid = am.roleid
WHERE r.rolname = 'lawliet_app';
