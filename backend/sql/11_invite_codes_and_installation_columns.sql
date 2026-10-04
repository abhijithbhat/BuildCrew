-- =====================================================================
-- 11_invite_codes_and_installation_columns.sql
-- 1) Invite codes currently live only in an in-memory dict + a local JSON
--    file (.invites_cache.json). On Render the filesystem is wiped on every
--    deploy/restart, so every shared "permanent" code silently dies.
--    Persist the code on the project row instead.
-- 2) github_installations.last_generated_at is written by the backend
--    (Generate Draft) but never created by any migration.
-- Safe to run more than once.
-- =====================================================================
ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS invite_code TEXT;

-- Case-insensitive uniqueness (the join screen says codes are case-insensitive).
CREATE UNIQUE INDEX IF NOT EXISTS projects_invite_code_key
  ON public.projects (upper(invite_code))
  WHERE invite_code IS NOT NULL;

ALTER TABLE public.github_installations
  ADD COLUMN IF NOT EXISTS last_generated_at TIMESTAMP WITH TIME ZONE;