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
    bot_username: str | None
    supabase_url: str
    supabase_service_role_key: str
    admin_id: int | None


def load_settings() -> Settings:
    values = {key: os.getenv(key, "").strip() for key in (
        "BOT_TOKEN", "CHANNEL_URL", "WEBHOOK_BASE_URL", "WEBHOOK_SECRET",
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    )}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError("Missing required environment variables: " + ", ".join(missing))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", values["WEBHOOK_SECRET"]):
        raise ValueError("WEBHOOK_SECRET must contain only letters, digits, '_' or '-'.")
    base_url = https_url(values["WEBHOOK_BASE_URL"], "WEBHOOK_BASE_URL")
    channel_url = https_url(values["CHANNEL_URL"], "CHANNEL_URL")
    supabase_url = https_url(values["SUPABASE_URL"], "SUPABASE_URL")
    if not values["SUPABASE_SERVICE_ROLE_KEY"]:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required.")
    path = os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip()
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
        raise ValueError("WEBHOOK_PATH must be an absolute URL path.")
    path = path.rstrip("/") or "/"
    try:
        port = int(os.getenv("PORT", "10000"))
        admin_raw = os.getenv("ADMIN_ID", "").strip()
        admin_id = int(admin_raw) if admin_raw else None
    except ValueError as exc:
        raise ValueError("PORT and ADMIN_ID must be integers when set.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    return Settings(
        bot_token=values["BOT_TOKEN"], channel_url=channel_url,
        webhook_base_url=base_url, webhook_secret=values["WEBHOOK_SECRET"],
        webhook_path=path, port=port,
        bot_username=os.getenv("BOT_USERNAME", "").strip().lstrip("@") or None,
        supabase_url=supabase_url, supabase_service_role_key=values["SUPABASE_SERVICE_ROLE_KEY"],
        admin_id=admin_id,
    )
