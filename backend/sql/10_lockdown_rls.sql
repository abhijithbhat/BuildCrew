-- =====================================================================
-- 10_lockdown_rls.sql  —  BuildCrew: close the direct-database back door
-- ---------------------------------------------------------------------
-- WHY: the Supabase anon key ships inside the APK (and is in main.dart on
-- a public repo). The current policies let ANYONE holding that key:
--   * read every profile (display_name falls back to the user's EMAIL),
--     every project, membership, role, and connected private repo name;
--   * (when logged in) insert/update rows directly through PostgREST —
--     e.g. insert a contribution with verification_status='confirmed' and
--     visibility='public', or add themselves to ANY project without an
--     invite code — bypassing every FastAPI check.
-- The mobile app never queries tables/storage directly (auth calls only)
-- and the backend uses the service-role key, which bypasses RLS. So no
-- table needs ANY policy. RLS stays ENABLED => default deny.
-- Safe to run more than once.
-- =====================================================================

-- 1) Make sure RLS is on for every app table.
ALTER TABLE public.profiles              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_members       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_agreements       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.github_installations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contributions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.confirmation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.confirmations         ENABLE ROW LEVEL SECURITY;

-- 2) Drop EVERY policy on the public schema (names-agnostic, so it also
--    removes policies created ad-hoc in the dashboard).
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT schemaname, tablename, policyname
    FROM pg_policies
    WHERE schemaname = 'public'
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I',
                   r.policyname, r.schemaname, r.tablename);
  END LOOP;
END $$;

-- 3) Storage: keep PUBLIC READ of the evidence bucket (passport links need
--    it) but remove client-side WRITE policies. Uploads go through
--    POST /contributions/upload-evidence using the service-role key.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT policyname
    FROM pg_policies
    WHERE schemaname = 'storage'
      AND tablename  = 'objects'
      AND cmd IN ('INSERT', 'UPDATE', 'DELETE', 'ALL')
      AND (COALESCE(qual, '') ILIKE '%evidence%'
           OR COALESCE(with_check, '') ILIKE '%evidence%')
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects', r.policyname);
  END LOOP;
END $$;

-- 4) Stop the signup trigger from storing the raw EMAIL as display_name
--    (that value was readable by anyone before step 2), and pin search_path
--    on the SECURITY DEFINER function (Supabase advisor warns without it).
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, github_username, avatar_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name',
                 NEW.raw_user_meta_data->>'name',
                 split_part(NEW.email, '@', 1)),
        NEW.raw_user_meta_data->>'preferred_username',
        NEW.raw_user_meta_data->>'avatar_url'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- Scrub rows that already hold a raw email as display_name.
UPDATE public.profiles
SET    display_name = split_part(display_name, '@', 1)
WHERE  display_name LIKE '%@%';

-- =====================================================================
-- VERIFY (run from your laptop; both must return [] or a 401/permission
-- error, NEVER user rows):
--   curl "$SUPABASE_URL/rest/v1/profiles?select=display_name" -H "apikey: $ANON_KEY"
--   curl "$SUPABASE_URL/rest/v1/projects?select=id,name"       -H "apikey: $ANON_KEY"
-- =====================================================================