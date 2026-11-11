-- ThemeGram: Telegram language-pack catalogue.
-- Run this migration in the Supabase SQL Editor before deploying the language catalogue feature.

CREATE TABLE IF NOT EXISTS public.telegram_languages (
    id text PRIMARY KEY,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    url text NOT NULL CHECK (url ~ '^https://(www[.])?t[.]me/setlanguage/[^/]+/?$'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS telegram_languages_name_idx
    ON public.telegram_languages (name);

ALTER TABLE public.telegram_languages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.telegram_languages FROM anon, authenticated;
