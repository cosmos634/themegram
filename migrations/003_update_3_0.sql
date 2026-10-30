-- ThemeGram Update 3.0: additive user-profile columns.
-- Run manually in Supabase SQL Editor. This migration does not drop or rename data.
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS language text,
    ADD COLUMN IF NOT EXISTS first_source text;

-- Existing users intentionally remain NULL in first_source. Application analytics
-- displays NULL/empty legacy values as "unknown"; do not backfill them as "direct".
