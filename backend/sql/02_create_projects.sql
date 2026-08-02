-- ========================================================
-- Supabase Schema: Projects Table
-- ========================================================

-- 1. Create public.projects table
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Allow anyone to view projects
CREATE POLICY "Projects are viewable by everyone."
    ON public.projects FOR SELECT
    USING (true);

-- Allow authenticated users to create projects
CREATE POLICY "Authenticated users can create projects."
    ON public.projects FOR INSERT
    WITH CHECK (auth.uid() = created_by);

-- Allow project creator to update project details
CREATE POLICY "Project creator can update project."
    ON public.projects FOR UPDATE
    USING (auth.uid() = created_by);
