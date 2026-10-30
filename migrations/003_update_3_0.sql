-- ThemeGram Update 3.0: additive user-profile columns.
-- Run manually in Supabase SQL Editor. This migration does not drop or rename data.
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS language text,
    ADD COLUMN IF NOT EXISTS first_source text;

-- Existing users intentionally remain NULL in first_source. Application analytics
-- displays NULL/empty legacy values as "unknown"; do not backfill them as "direct".

-- Enforce first-touch attribution at the database boundary as well as in SQLite.
CREATE OR REPLACE FUNCTION public.themegram_keep_first_source()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.first_source IS NOT NULL THEN
        NEW.first_source := OLD.first_source;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_keep_first_source ON public.users;
CREATE TRIGGER users_keep_first_source
BEFORE UPDATE OF first_source ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.themegram_keep_first_source();
