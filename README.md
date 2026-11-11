# ThemeGram

ThemeGram is an Uzbek- and Russian-language Telegram bot for browsing iOS and Android Telegram themes and generating custom Telegram Android themes from images. It uses aiogram 3, aiohttp webhooks, Supabase, and a local SQLite cache.

## Features
- iOS / Android themes in Dark, Soft, Anime, Boshqa categories.
- Image-to-theme generator for Telegram Android: send a JPG, PNG, or WEBP image, choose the theme filename, and receive a named .attheme file.
- Growth Dashboard tracks successful generated themes alongside the existing product-usage events.
- Random active theme selection without immediate repeats when alternatives exist.
- Exactly up to 50 active themes cached per platform/category (8 groups total).
- Theme cache warms at startup and refreshes in the background every hour. Users get themes from the in-memory snapshot only; failed refreshes keep the last successful snapshot.
- User profiles and temporary user state are cached in SQLite. Normal interactions read and write local state; a missing state is fetched from Supabase once.
- Dirty local profile/state changes sync to Supabase hourly. Failed writes remain dirty for a later retry. Remote states are merged without overwriting local unsynced changes.
- State expires after one hour.
- Admin panel at `/admin`: statistics, add/list/filter/edit/delete themes and Telegram language links, plus confirmed Uzbek/Russian/all-user broadcasts.
- Telegram language catalogue is managed in Supabase; users can browse language packs and open their Telegram installation links. Growth Dashboard records language-card views and install-button clicks.
- Telegram webhook, `/health` endpoint, and Render deployment.

## Environment
Required: `BOT_TOKEN`, `CHANNEL_URL`, `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Set `ADMIN_ID` to enable admin access.
Optional: `BOT_USERNAME`, `WEBHOOK_PATH` (default `/telegram/webhook`), `PORT` (default `10000`), `STATE_CACHE_PATH` (default `themegram_cache.sqlite3`), `ATTHEME_API_URL`, and `ATTHEME_API_KEY`.

## Attheme generator setup
Set `ATTHEME_API_URL` to the deployed generator API origin (without `/api/v1/generate`) and `ATTHEME_API_KEY` to the same secret configured as `API_KEY` on that API. Both values are required to enable the “Tema yaratish” reply-keyboard button. The API key stays on the bot server and is never sent to Telegram users. This generator currently creates themes for Telegram Android only.

## Local setup
1. Use Python 3.11+ and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in secrets.
3. Set a public HTTPS `WEBHOOK_BASE_URL` for webhook testing.
4. Run `python bot.py`. The app intentionally does not fall back to polling.

## Cache and indexes
Theme selection never queries Supabase per user interaction. Startup loads up to 50 active themes for each platform/category pair into memory; an hourly background task replaces the full snapshot only when all eight groups load successfully. Admin add/edit/delete operations refresh the snapshot immediately.

SQLite stores user profiles and temporary state locally. Updates are marked dirty until Supabase accepts the hourly upsert; failed syncs retain those dirty records for retry. At startup, the bot loads remote states into the local cache, while local dirty states take precedence. SQLite is stored outside Git via `.gitignore`; set `STATE_CACHE_PATH` if a different writable location is needed.

The query filters active themes by `platform` and `category`. This partial composite index can support that lookup:

```sql
CREATE INDEX IF NOT EXISTS idx_themes_active_platform_category
ON public.themes (platform, category)
WHERE is_active IS TRUE;
```

Apply `migrations/005_language_catalog.sql` in the Supabase SQL Editor before using the language catalogue. Keep secrets out of GitHub and keep the Supabase service-role key server-side.

## Render
Configure the required environment variables in Render; `SUPABASE_URL` is already set in `render.yaml`. Add `ATTHEME_API_URL` and `ATTHEME_API_KEY` to the ThemeGram web service environment to enable theme generation. The service runs `python bot.py` and exposes `/health`; verify it returns HTTP 200 and configure UptimeRobot against that path. The deployment filesystem must allow the service to create its SQLite cache. If Render watches `main`, a push to `main` triggers deployment after the PR is merged.

## Tests
Run `python -m unittest discover -s tests -v`. Unit tests use mocks and do not need live credentials. Live Supabase, Telegram broadcast, and deployed webhook behavior still need deployment-time verification.
