-- ========================================================
-- Supabase Schema: Confirmations Table
-- ========================================================

-- 1. Create public.confirmations table
CREATE TABLE IF NOT EXISTS public.confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contribution_id UUID REFERENCES public.contributions(id) ON DELETE CASCADE NOT NULL,
    confirmed_by_user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('confirm', 'dispute')),
    confirmed_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    notes TEXT,
    UNIQUE(contribution_id, confirmed_by_user_id)
);

-- 2. Enable Row Level Security (RLS)
ALTER TABLE public.confirmations ENABLE ROW LEVEL SECURITY;

-- 3. Create RLS Policies
-- Allow anyone to view confirmations
CREATE POLICY "Confirmations are viewable by everyone."
    ON public.confirmations FOR SELECT
    USING (true);

-- Allow authenticated users to submit a confirmation or dispute
CREATE POLICY "Users can submit confirmations."
    ON public.confirmations FOR INSERT
    WITH CHECK (auth.uid() = confirmed_by_user_id);

-- Allow users to update their own confirmation or dispute
CREATE POLICY "Users can update their own confirmation."
    ON public.confirmations FOR UPDATE
    USING (auth.uid() = confirmed_by_user_id);

-- Allow users to delete their own confirmation or dispute
CREATE POLICY "Users can delete their own confirmation."
    ON public.confirmations FOR DELETE
    USING (auth.uid() = confirmed_by_user_id);
