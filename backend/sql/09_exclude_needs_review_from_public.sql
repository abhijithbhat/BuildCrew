-- ========================================================
-- Supabase Migration: Exclude 'needs-review' & disputed contributions from public SELECT
-- ========================================================

-- Update RLS SELECT policy on public.contributions so that public visibility
-- strictly requires verification_status != 'needs-review' and dispute_state != 'disputed'.

DROP POLICY IF EXISTS "Contributions are viewable based on visibility." ON public.contributions;

CREATE POLICY "Contributions are viewable based on visibility."
    ON public.contributions FOR SELECT
    USING (
        (visibility = 'public' AND verification_status != 'needs-review' AND dispute_state != 'disputed')
        OR contributor = auth.uid()
        OR confirmed_by = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.projects WHERE id = project AND created_by = auth.uid()
        )
    );
