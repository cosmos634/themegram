# ThemeGram

ThemeGram is an Uzbek-language Telegram bot for browsing iOS and Android Telegram themes. It uses aiogram 3, aiohttp webhooks, and Supabase.

## Features
- iOS / Android themes in Dark, Soft, Anime, Boshqa categories.
- Random active theme selection without immediate repeats when alternatives exist.
- Supabase user profiles and temporary state; state expires after one hour.
- Admin panel at `/admin`: statistics, add/list/filter/edit/delete themes, and confirmed broadcast.
- Telegram webhook, `/health` endpoint, and Render deployment.

## Environment
Required: `BOT_TOKEN`, `CHANNEL_URL`, `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Set `ADMIN_ID` to enable admin access.
Optional: `BOT_USERNAME`, `WEBHOOK_PATH` (default `/telegram/webhook`), `PORT` (default `10000`), and `THEME_CACHE_TTL_SECONDS` (active-theme cache TTL, default `60`; use `0` to disable cache reuse).

## Local setup
1. Use Python 3.11+ and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in secrets.
3. Set a public HTTPS `WEBHOOK_BASE_URL` for webhook testing.
4. Run `python bot.py`. The app intentionally does not fall back to polling.

## Cache and indexes
Active themes are cached per platform/category in process memory for 60 seconds by default. Concurrent misses share a refresh; add/edit/delete operations invalidate the cache. If Supabase temporarily fails, an expired cache is served stale rather than discarded. Cache entries are instance-local, so separate bot instances refresh independently and changes made outside the bot can remain cached until TTL expiry.

The query filters active themes by `platform` and `category`. After reviewing existing indexes for an equivalent, the following idempotent partial composite index can support that exact lookup while indexing only active rows:

```sql
CREATE INDEX IF NOT EXISTS idx_themes_active_platform_category
ON public.themes (platform, category)
WHERE is_active IS TRUE;
```

No schema changes are required. Keep secrets out of GitHub and keep the Supabase service-role key server-side.

## Render
Configure the required environment variables in Render; `SUPABASE_URL` is already set in `render.yaml`. The service runs `python bot.py` and exposes `/health`; verify it returns HTTP 200 and configure UptimeRobot against that path. If Render watches `main`, a push to `main` triggers its deployment.

## Tests
Run `python -m unittest discover -s tests -v`. Unit tests use mocks and do not need live credentials. Live Supabase, Telegram broadcast, and deployed webhook behavior need deployment-time verification.
