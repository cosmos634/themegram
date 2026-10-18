# ThemeGram

ThemeGram is an Uzbek-language Telegram bot for browsing iOS and Android themes. It uses aiogram 3, a JSON theme catalogue, SQLite temporary state, and Telegram webhooks.

## Features
- iOS / Android selection and four theme categories: Dark, Soft, Anime, Boshqa.
- Random theme selection, install URL, next theme, and navigation.
- SQLite state expires after 1 hour of inactivity.
- Webhook mode, a `/health` endpoint, and Render deployment configuration.
- Theme data is kept separate from Python code.

## Requirements
Python 3.11+ and a Telegram bot token from BotFather.

## Local setup
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Linux/macOS:
   source .venv/bin/activate
   # Windows:
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set the required values.
3. For local webhook testing, expose your local HTTP port through a trusted HTTPS tunnel and set `WEBHOOK_BASE_URL` to that HTTPS URL. Telegram webhooks require a publicly reachable HTTPS endpoint.
4. Run `python bot.py`.

The bot intentionally does not use polling. A local run without a public webhook URL will fail configuration validation rather than silently switching modes.

## Environment variables
- `BOT_TOKEN`: required Telegram bot token.
- `BOT_USERNAME`: optional username, without @.
- `CHANNEL_URL`: required HTTPS URL opened by the channel keyboard button.
- `WEBHOOK_BASE_URL`: public HTTPS base URL of the deployed service, without a trailing slash.
- `WEBHOOK_SECRET`: required secret token for Telegram webhook validation (letters, digits, underscore, or hyphen; 1–256 characters).
- `WEBHOOK_PATH`: optional webhook path, defaults to `/telegram/webhook`.
- `PORT`: port provided by Render; defaults to 10000 locally.
- `DATABASE_PATH`: optional SQLite file path, defaults to `data/themegram.sqlite3`.

Never commit your real `.env` file or credentials.

## Theme JSON schema
`data/themes.json` has top-level keys `iOS` and `Android`; each contains `Dark`, `Soft`, `Anime`, and `Boshqa` arrays. Each theme object uses:
```json
{
  "id": "unique-id",
  "name": "Theme name",
  "url": "https://example.com/actual-theme",
  "description": "Optional description"
}
```
The shipped JSON uses empty arrays because no real, verified theme links were supplied. Add genuine links before launch; do not treat example URLs as real themes. URLs must use HTTPS.

## Render deployment
1. Push this repository to GitHub.
2. In Render, create a Web Service from the repository. The included `render.yaml` describes the service and health check.
3. Add `BOT_TOKEN`, `CHANNEL_URL`, `WEBHOOK_BASE_URL`, and `WEBHOOK_SECRET` as environment variables. Set `WEBHOOK_BASE_URL` to the service's actual public HTTPS URL, such as `https://your-service.onrender.com`.
4. Deploy and verify `https://your-service.onrender.com/health` returns HTTP 200.
5. In UptimeRobot, create an HTTP(s) monitor for that health URL.

UptimeRobot checks availability; periodic pings do not guarantee that a free Render service remains awake. A filesystem on a free service may be ephemeral. If state must survive deployments/restarts, configure storage supported by your Render plan and set `DATABASE_PATH` to a path on that persistent disk. Since state expires after one hour, loss of temporary state may be acceptable for a prototype.

## Tests
Run `python -m unittest discover -s tests -v`. Tests do not require a real Telegram token.
