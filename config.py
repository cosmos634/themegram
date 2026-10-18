"""Environment configuration."""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def https_url(value: str, name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{name} must be a valid HTTPS URL.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    channel_url: str
    webhook_base_url: str
    webhook_secret: str
    webhook_path: str
    port: int
    database_path: Path
    bot_username: str | None


def load_settings() -> Settings:
    values = {key: os.getenv(key, "").strip() for key in (
        "BOT_TOKEN", "CHANNEL_URL", "WEBHOOK_BASE_URL", "WEBHOOK_SECRET"
    )}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError("Missing required environment variables: " + ", ".join(missing))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", values["WEBHOOK_SECRET"]):
        raise ValueError("WEBHOOK_SECRET must contain only letters, digits, '_' or '-'.")
    base_url = https_url(values["WEBHOOK_BASE_URL"], "WEBHOOK_BASE_URL")
    channel_url = https_url(values["CHANNEL_URL"], "CHANNEL_URL")
    path = os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip()
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise ValueError("WEBHOOK_PATH must be an absolute URL path.")
    path = path.rstrip("/") or "/"
    try:
        port = int(os.getenv("PORT", "10000"))
    except ValueError as exc:
        raise ValueError("PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    db_path = Path(os.getenv("DATABASE_PATH", "data/themegram.sqlite3"))
    if not db_path.is_absolute():
        db_path = (BASE_DIR / db_path).resolve()
    return Settings(
        bot_token=values["BOT_TOKEN"], channel_url=channel_url,
        webhook_base_url=base_url, webhook_secret=values["WEBHOOK_SECRET"],
        webhook_path=path, port=port, database_path=db_path,
        bot_username=os.getenv("BOT_USERNAME", "").strip().lstrip("@") or None,
    )
