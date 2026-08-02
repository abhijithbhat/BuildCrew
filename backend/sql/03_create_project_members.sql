-- ========================================================
-- Supabase Schema: Project Members Table
-- ========================================================

-- 1. Create public.project_members table
CREATE TABLE IF NOT EXISTS public.project_members (
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.project_members ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Allow anyone to view project members
CREATE POLICY "Project members are viewable by everyone."
    ON public.project_members FOR SELECT
    USING (true);

-- Allow users to join or project owner to add members
CREATE POLICY "Users can join or be added to projects."
    ON public.project_members FOR INSERT
    WITH CHECK (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

-- Allow members or project owner to update member roles
CREATE POLICY "Members or project owner can update roles."
    ON public.project_members FOR UPDATE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

-- Allow members or project owner to remove members
CREATE POLICY "Members or project owner can remove members."
    ON public.project_members FOR DELETE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));
