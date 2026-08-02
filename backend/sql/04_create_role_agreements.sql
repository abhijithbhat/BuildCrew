-- ========================================================
-- Supabase Schema: Role Agreements Table
-- ========================================================

-- 1. Create public.role_agreements table
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

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.role_agreements ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Allow anyone to view role agreements
CREATE POLICY "Role agreements are viewable by everyone."
    ON public.role_agreements FOR SELECT
    USING (true);

-- Allow users or project owners to create role agreements
CREATE POLICY "Users or project owners can create role agreements."
    ON public.role_agreements FOR INSERT
    WITH CHECK (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

-- Allow users or project owners to update role agreements
CREATE POLICY "Users or project owners can update role agreements."
    ON public.role_agreements FOR UPDATE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));

-- Allow users or project owners to delete role agreements
CREATE POLICY "Users or project owners can delete role agreements."
    ON public.role_agreements FOR DELETE
    USING (auth.uid() = user_id OR EXISTS (
        SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
    ));
