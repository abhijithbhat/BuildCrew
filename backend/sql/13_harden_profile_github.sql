-- =====================================================================
-- 13_harden_profile_github.sql
-- profiles.github_username must only come from a GitHub-verified sign-in.
-- Before: handle_new_user() copied user_metadata.preferred_username, which any
-- client holding the public anon key can set when it calls Supabase Auth
-- directly. After: only the server-controlled app_metadata.provider = 'github'
-- can set it. Safe to run more than once.
-- =====================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, github_username, avatar_url)
    VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.raw_user_meta_data->>'full_name', ''),
                 NULLIF(NEW.raw_user_meta_data->>'name', ''),
                 NULLIF(split_part(COALESCE(NEW.email, ''), '@', 1), '')),
        CASE WHEN NEW.raw_app_meta_data->>'provider' = 'github'
             THEN COALESCE(NULLIF(NEW.raw_user_meta_data->>'user_name', ''),
                           NULLIF(NEW.raw_user_meta_data->>'preferred_username', ''))
             ELSE NULL
        END,
        NULLIF(NEW.raw_user_meta_data->>'avatar_url', '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

UPDATE public.profiles p
SET    github_username = NULL
WHERE  p.github_username IS NOT NULL
  AND  NOT EXISTS (
         SELECT 1
         FROM   auth.identities i
         WHERE  i.user_id = p.id
           AND  i.provider = 'github'
       );