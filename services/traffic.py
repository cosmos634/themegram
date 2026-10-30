"""Telegram deep-link attribution helpers."""
import re

# Telegram deep-link start payloads are limited to 64 URL-safe characters.
_SOURCE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def parse_start_source(payload: str | None) -> str:
    if payload is None or payload == "":
        return "direct"
    if not _SOURCE_RE.fullmatch(payload):
        return "unknown"
    return payload.lower()
