-- ========================================================
-- Supabase Schema: GitHub Installations Table
-- ========================================================

-- 1. Create public.github_installations table
CREATE TABLE IF NOT EXISTS public.github_installations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE NOT NULL,
    installation_id TEXT NOT NULL,
    repo_full_name TEXT NOT NULL,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    UNIQUE(project_id, repo_full_name)
);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.github_installations ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Allow anyone to view GitHub installations
CREATE POLICY "GitHub installations are viewable by everyone."
    ON public.github_installations FOR SELECT
    USING (true);

-- Allow project owner or members to add GitHub installations
CREATE POLICY "Project members can add GitHub installations."
    ON public.github_installations FOR INSERT
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ) OR EXISTS (
        SELECT 1 FROM public.project_members WHERE project_id = github_installations.project_id AND user_id = auth.uid()
    ));

-- Allow project owner to update GitHub installations
CREATE POLICY "Project owner can update GitHub installations."
    ON public.github_installations FOR UPDATE
    USING (EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

-- Allow project owner to delete GitHub installations
CREATE POLICY "Project owner can delete GitHub installations."
    ON public.github_installations FOR DELETE
    USING (EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));
