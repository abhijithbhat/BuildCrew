-- ========================================================
-- BUILDCREW MASTER SUPABASE DATABASE SCHEMA (Idempotent)
-- Execute this file in Supabase Dashboard -> SQL Editor
-- ========================================================

-- 1. PROFILES TABLE & AUTH TRIGGER
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    github_username TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public profiles are viewable by everyone." ON public.profiles;
CREATE POLICY "Public profiles are viewable by everyone."
    ON public.profiles FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can insert their own profile." ON public.profiles;
CREATE POLICY "Users can insert their own profile."
    ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update their own profile." ON public.profiles;
CREATE POLICY "Users can update their own profile."
    ON public.profiles FOR UPDATE USING (auth.uid() = id);

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, github_username, avatar_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', NEW.email),
        NEW.raw_user_meta_data->>'preferred_username',
        NEW.raw_user_meta_data->>'avatar_url'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- 2. PROJECTS TABLE
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Projects are viewable by everyone." ON public.projects;
CREATE POLICY "Projects are viewable by everyone."
    ON public.projects FOR SELECT USING (true);

DROP POLICY IF EXISTS "Authenticated users can create projects." ON public.projects;
CREATE POLICY "Authenticated users can create projects."
    ON public.projects FOR INSERT WITH CHECK (auth.uid() = created_by);

DROP POLICY IF EXISTS "Project creator can update project." ON public.projects;
CREATE POLICY "Project creator can update project."
    ON public.projects FOR UPDATE USING (auth.uid() = created_by);

DROP POLICY IF EXISTS "Project creator can delete project." ON public.projects;
CREATE POLICY "Project creator can delete project."
    ON public.projects FOR DELETE USING (auth.uid() = created_by);



-- 3. PROJECT MEMBERS TABLE
CREATE TABLE IF NOT EXISTS public.project_members (
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

ALTER TABLE public.project_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Project members are viewable by everyone." ON public.project_members;
CREATE POLICY "Project members are viewable by everyone."
    ON public.project_members FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can join or be added to projects." ON public.project_members;
CREATE POLICY "Users can join or be added to projects."
    ON public.project_members FOR INSERT
    WITH CHECK (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

DROP POLICY IF EXISTS "Members or project owner can update roles." ON public.project_members;
CREATE POLICY "Members or project owner can update roles."
    ON public.project_members FOR UPDATE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

DROP POLICY IF EXISTS "Members or project owner can remove members." ON public.project_members;
CREATE POLICY "Members or project owner can remove members."
    ON public.project_members FOR DELETE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));


-- 4. ROLE AGREEMENTS TABLE
CREATE TABLE IF NOT EXISTS public.role_agreements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    declared_role TEXT NOT NULL,
    responsibilities TEXT,
    deadline TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE public.role_agreements ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Role agreements are viewable by everyone." ON public.role_agreements;
CREATE POLICY "Role agreements are viewable by everyone."
    ON public.role_agreements FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users or project owners can create role agreements." ON public.role_agreements;
CREATE POLICY "Users or project owners can create role agreements."
    ON public.role_agreements FOR INSERT
    WITH CHECK (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

DROP POLICY IF EXISTS "Users or project owners can update role agreements." ON public.role_agreements;
CREATE POLICY "Users or project owners can update role agreements."
    ON public.role_agreements FOR UPDATE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

DROP POLICY IF EXISTS "Users or project owners can delete role agreements." ON public.role_agreements;
CREATE POLICY "Users or project owners can delete role agreements."
    ON public.role_agreements FOR DELETE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));


-- 5. GITHUB INSTALLATIONS TABLE
CREATE TABLE IF NOT EXISTS public.github_installations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE NOT NULL,
    installation_id TEXT NOT NULL,
    repo_full_name TEXT NOT NULL,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE(project_id, repo_full_name)
);

ALTER TABLE public.github_installations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "GitHub installations are viewable by everyone." ON public.github_installations;
CREATE POLICY "GitHub installations are viewable by everyone."
    ON public.github_installations FOR SELECT USING (true);

DROP POLICY IF EXISTS "Project members can add GitHub installations." ON public.github_installations;
CREATE POLICY "Project members can add GitHub installations."
    ON public.github_installations FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ) OR EXISTS (
        SELECT 1 FROM public.project_members WHERE project_id = github_installations.project_id AND user_id = auth.uid()
    ));

DROP POLICY IF EXISTS "Project owner can update GitHub installations." ON public.github_installations;
CREATE POLICY "Project owner can update GitHub installations."
    ON public.github_installations FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

DROP POLICY IF EXISTS "Project owner can delete GitHub installations." ON public.github_installations;
CREATE POLICY "Project owner can delete GitHub installations."
    ON public.github_installations FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));


-- 6. CONTRIBUTIONS TABLE
CREATE TABLE IF NOT EXISTS public.contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contributor UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    project UUID REFERENCES public.projects(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    description TEXT,
    date_range TEXT,
    source_type TEXT,
    evidence_link TEXT,
    verification_status TEXT NOT NULL DEFAULT 'pending',
    confirmed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    visibility TEXT NOT NULL DEFAULT 'public',
    dispute_state TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

ALTER TABLE public.contributions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Contributions are viewable based on visibility." ON public.contributions;
CREATE POLICY "Contributions are viewable based on visibility."
    ON public.contributions FOR SELECT
    USING (
        visibility = 'public'
        OR contributor = auth.uid()
        OR confirmed_by = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project AND created_by = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Contributors can submit contributions." ON public.contributions;
CREATE POLICY "Contributors can submit contributions."
    ON public.contributions FOR INSERT WITH CHECK (auth.uid() = contributor);

DROP POLICY IF EXISTS "Contributor or project owner can update contributions." ON public.contributions;
CREATE POLICY "Contributor or project owner can update contributions."
    ON public.contributions FOR UPDATE
    USING (
        auth.uid() = contributor
        OR auth.uid() = confirmed_by
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project AND created_by = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Contributor or project owner can delete contributions." ON public.contributions;
CREATE POLICY "Contributor or project owner can delete contributions."
    ON public.contributions FOR DELETE
    USING (
        auth.uid() = contributor
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project AND created_by = auth.uid()
        )
    );


-- 7. CONFIRMATIONS TABLE
CREATE TABLE IF NOT EXISTS public.confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contribution_id UUID REFERENCES public.contributions(id) ON DELETE CASCADE NOT NULL,
    confirmed_by_user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('confirm', 'dispute')),
    confirmed_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    notes TEXT,
    UNIQUE(contribution_id, confirmed_by_user_id)
);

ALTER TABLE public.confirmations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Confirmations are viewable by everyone." ON public.confirmations;
CREATE POLICY "Confirmations are viewable by everyone."
    ON public.confirmations FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can submit confirmations." ON public.confirmations;
CREATE POLICY "Users can submit confirmations."
    ON public.confirmations FOR INSERT WITH CHECK (auth.uid() = confirmed_by_user_id);

DROP POLICY IF EXISTS "Users can update their own confirmation." ON public.confirmations;
CREATE POLICY "Users can update their own confirmation."
    ON public.confirmations FOR UPDATE USING (auth.uid() = confirmed_by_user_id);

DROP POLICY IF EXISTS "Users can delete their own confirmation." ON public.confirmations;
CREATE POLICY "Users can delete their own confirmation."
    ON public.confirmations FOR DELETE USING (auth.uid() = confirmed_by_user_id);


-- 8. STORAGE BUCKETS (EVIDENCE UPLOADS)
INSERT INTO storage.buckets (id, name, public)
VALUES ('evidence', 'evidence', true)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "Authenticated users can upload evidence files." ON storage.objects;
CREATE POLICY "Authenticated users can upload evidence files."
    ON storage.objects FOR INSERT
    TO authenticated
    WITH CHECK (bucket_id = 'evidence');

DROP POLICY IF EXISTS "Anyone can view evidence files." ON storage.objects;
CREATE POLICY "Anyone can view evidence files."
    ON storage.objects FOR SELECT
    USING (bucket_id = 'evidence');

DROP POLICY IF EXISTS "Users can update their own evidence files." ON storage.objects;
CREATE POLICY "Users can update their own evidence files."
    ON storage.objects FOR UPDATE
    TO authenticated
    USING (bucket_id = 'evidence' AND auth.uid()::text = (storage.foldername(name))[1]);

DROP POLICY IF EXISTS "Users can delete their own evidence files." ON storage.objects;
CREATE POLICY "Users can delete their own evidence files."
    ON storage.objects FOR DELETE
    TO authenticated
    USING (bucket_id = 'evidence' AND auth.uid()::text = (storage.foldername(name))[1]);

