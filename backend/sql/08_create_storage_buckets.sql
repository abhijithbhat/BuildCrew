-- ========================================================
-- Supabase Schema: Storage Buckets (Evidence Uploads)
-- ========================================================

-- 1. Insert 'evidence' public bucket if not already existing
INSERT INTO storage.buckets (id, name, public)
VALUES ('evidence', 'evidence', true)
ON CONFLICT (id) DO NOTHING;

-- 2. Allow authenticated users to upload evidence files
CREATE POLICY "Authenticated users can upload evidence files."
    ON storage.objects FOR INSERT
    TO authenticated
    WITH CHECK (bucket_id = 'evidence');

-- 3. Allow public access to view/download evidence files
CREATE POLICY "Anyone can view evidence files."
    ON storage.objects FOR SELECT
    USING (bucket_id = 'evidence');

-- 4. Allow users to update/delete their own evidence files
CREATE POLICY "Users can update their own evidence files."
    ON storage.objects FOR UPDATE
    TO authenticated
    USING (bucket_id = 'evidence' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can delete their own evidence files."
    ON storage.objects FOR DELETE
    TO authenticated
    USING (bucket_id = 'evidence' AND auth.uid()::text = (storage.foldername(name))[1]);
