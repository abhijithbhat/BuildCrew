-- ========================================================
-- Supabase Schema: Contributions Table
-- ========================================================

-- 1. Create public.contributions table
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

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.contributions ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Allow viewing public contributions or team members viewing project contributions
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

-- Allow contributors to submit contributions
CREATE POLICY "Contributors can submit contributions."
    ON public.contributions FOR INSERT
    WITH CHECK (auth.uid() = contributor);

-- Allow contributor, project owner, or confirming user to update contributions
CREATE POLICY "Contributor or project owner can update contributions."
    ON public.contributions FOR UPDATE
    USING (
        auth.uid() = contributor
        OR auth.uid() = confirmed_by
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project AND created_by = auth.uid()
        )
    );

-- Allow contributor or project owner to delete contributions
CREATE POLICY "Contributor or project owner can delete contributions."
    ON public.contributions FOR DELETE
    USING (
        auth.uid() = contributor
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project AND created_by = auth.uid()
        )
    );
