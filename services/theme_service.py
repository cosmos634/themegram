"""Theme catalogue validation and random selection."""
import json
import random
from pathlib import Path
from urllib.parse import urlparse

OPERATING_SYSTEMS = {"iOS", "Android"}
CATEGORIES = {"Dark", "Soft", "Anime", "Boshqa"}


class ThemeDataError(Exception):
    pass


class ThemeService:
    def __init__(self, json_path: Path):
        self.json_path = Path(json_path)
        self._themes = {}

    @staticmethod
    def valid_url(url: object) -> bool:
        if not isinstance(url, str) or len(url) > 2048:
            return False
        try:
            parsed = urlparse(url)
            return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
        except ValueError:
            return False

    def load(self) -> None:
        try:
            with self.json_path.open(encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError as exc:
            raise ThemeDataError(f"Theme JSON not found: {self.json_path}") from exc
        except json.JSONDecodeError as exc:
            raise ThemeDataError("Theme JSON is malformed.") from exc
        if not isinstance(data, dict):
            raise ThemeDataError("Theme JSON root must be an object.")
        for os_name in OPERATING_SYSTEMS:
            section = data.get(os_name)
            if not isinstance(section, dict):
                raise ThemeDataError(f"Missing or invalid OS section: {os_name}")
            for category in CATEGORIES:
                items = section.get(category)
                if not isinstance(items, list):
                    raise ThemeDataError(f"{os_name}.{category} must be a list.")
                ids = set()
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        raise ThemeDataError(f"Invalid theme at {os_name}.{category}[{index}].")
                    theme_id, name, url = item.get("id"), item.get("name"), item.get("url")
                    if not isinstance(theme_id, str) or not theme_id.strip() or theme_id in ids:
                        raise ThemeDataError(f"Invalid or duplicate theme id in {os_name}.{category}.")
                    if not isinstance(name, str) or not name.strip() or not self.valid_url(url):
                        raise ThemeDataError(f"Theme {theme_id!r} needs a name and valid HTTPS URL.")
                    if "description" in item and not isinstance(item["description"], str):
                        raise ThemeDataError(f"Theme {theme_id!r} description must be text.")
                    ids.add(theme_id)
        self._themes = data

    def get_random(self, os_name: str, category: str, previous_id: str | None = None):
        if os_name not in OPERATING_SYSTEMS or category not in CATEGORIES:
            raise ValueError("Unsupported OS or category.")
        items = self._themes[os_name][category]
        if not items:
            return None
        choices = [item for item in items if item["id"] != previous_id]
        return dict(random.choice(choices or items))
