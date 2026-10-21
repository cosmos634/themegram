# ThemeGram

ThemeGram is an Uzbek-language Telegram bot for browsing iOS and Android Telegram themes. It uses aiogram 3, aiohttp webhooks, and Supabase as the single source of truth for themes, users, and temporary user selections.

## Features
- iOS / Android selection and Dark, Soft, Anime, Boshqa categories.
- Random active theme selection without immediate repeats when alternatives exist.
- Supabase-backed user profiles and temporary selection state; stale state expires after one hour.
- Admin panel at `/admin`: statistics, add/list/filter/edit/delete themes, and confirmed broadcast.
- Broadcast supports Telegram messages/media through `copy_message`, retry-after handling, and a result report.
- Webhook mode, `/health` endpoint, and Render deployment configuration.

## Environment variables
Required:
- `BOT_TOKEN`: Telegram bot token.
- `CHANNEL_URL`: HTTPS URL opened by the channel keyboard button.
- `WEBHOOK_BASE_URL`: public HTTPS service URL, without a trailing slash.
- `WEBHOOK_SECRET`: Telegram webhook validation secret.
- `SUPABASE_URL`: Supabase project URL.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side secret key. Never commit or log it.
- `ADMIN_ID`: Telegram numeric user ID permitted to use the admin panel. If omitted, admin features are disabled.

Optional: `BOT_USERNAME`, `WEBHOOK_PATH` (defaults to `/telegram/webhook`), `PORT` (defaults to 10000), and `THEME_CACHE_TTL_SECONDS` (defaults to 60; set to 0 to disable theme caching).

## Local setup
1. Install Python 3.11+ and dependencies: `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in secrets.
3. For local webhook testing, expose the local port through a trusted HTTPS tunnel and set `WEBHOOK_BASE_URL` to its HTTPS URL.
4. Run `python bot.py`. The application intentionally does not fall back to polling.

## Supabase schema
The application expects the existing `public.themes`, `public.users`, `public.user_states`, and optional `public.user_activity` tables described in the deployment instructions. No schema recreation or destructive SQL is required. Row Level Security remains enabled; the service-role/secret key is used only by the server-side process.

Theme URL validation expects Telegram theme links in the form `https://t.me/addtheme/...`. Active themes are cached in memory per platform/category for the configured TTL. Cache instances are local to each running bot process; successful admin create/edit/delete operations invalidate the local cache.

## Optional theme-query index

Run this idempotent SQL in the Supabase SQL Editor if the query plan indicates that active-theme filtering needs an index:

```sql
create index if not exists themes_active_platform_category_idx
on public.themes (platform, category, id)
where is_active = true;
```

This partial composite index can help queries filtering by `is_active`, `platform`, and `category`; verify with `EXPLAIN (ANALYZE, BUFFERS)` on representative data before and after. It is optional and does not change the schema or data.

## Render deployment
Set `BOT_TOKEN`, `CHANNEL_URL`, `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, and `ADMIN_ID` in Render. `SUPABASE_URL` is prefilled in `render.yaml` for this project. After deploy, verify `https://your-service.onrender.com/health` returns HTTP 200 and monitor it with UptimeRobot.

## Tests
Run:
```bash
python -m unittest discover -s tests -v
```
Tests use mocks and do not need a real Telegram token or Supabase secret. Live database operations, Telegram broadcast delivery, and the Render webhook still require deployment-time verification.
