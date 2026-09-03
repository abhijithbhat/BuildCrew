-- ========================================================
-- Supabase Schema: Confirmation Requests Table
-- ========================================================

-- 1. Create public.confirmation_requests table
CREATE TABLE IF NOT EXISTS public.confirmation_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contribution_id UUID REFERENCES public.contributions(id) ON DELETE CASCADE NOT NULL,
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE NOT NULL,
    requested_by UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    reviewer_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'disputed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 2. Indexes for fast reviewer lookup and contribution joins
CREATE INDEX IF NOT EXISTS idx_confirmation_requests_reviewer ON public.confirmation_requests(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_confirmation_requests_contrib ON public.confirmation_requests(contribution_id);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE public.confirmation_requests ENABLE ROW LEVEL SECURITY;

-- 4. Create RLS Policies
-- Allow viewing if user is requester, reviewer, or project creator
DROP POLICY IF EXISTS "Confirmation requests are viewable by participants or project owner." ON public.confirmation_requests;
CREATE POLICY "Confirmation requests are viewable by participants or project owner."
    ON public.confirmation_requests FOR SELECT
    USING (
        auth.uid() = requested_by
        OR auth.uid() = reviewer_id
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
        )
    );

-- Allow requester to create requests
DROP POLICY IF EXISTS "Contributors can create confirmation requests." ON public.confirmation_requests;
CREATE POLICY "Contributors can create confirmation requests."
    ON public.confirmation_requests FOR INSERT
    WITH CHECK (auth.uid() = requested_by);

-- Allow reviewer or requester to update confirmation request
DROP POLICY IF EXISTS "Participants can update confirmation requests." ON public.confirmation_requests;
CREATE POLICY "Participants can update confirmation requests."
    ON public.confirmation_requests FOR UPDATE
    USING (
        auth.uid() = reviewer_id
        OR auth.uid() = requested_by
    );

-- Allow project owner or requester to delete confirmation request
DROP POLICY IF EXISTS "Participants can delete confirmation requests." ON public.confirmation_requests;
CREATE POLICY "Participants can delete confirmation requests."
    ON public.confirmation_requests FOR DELETE
    USING (
        auth.uid() = requested_by
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project_id AND created_by = auth.uid()
        )
    );
