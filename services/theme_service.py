"""Supabase-backed theme service."""
from database.supabase import SupabaseDB

OPERATING_SYSTEMS = {"iOS", "Android"}
CATEGORIES = {"Dark", "Soft", "Anime", "Boshqa"}


class ThemeService:
    def __init__(self, db: SupabaseDB):
        self.db = db

    async def get_random(self, os_name: str, category: str, previous_id: str | None = None):
        if os_name not in OPERATING_SYSTEMS or category not in CATEGORIES:
            raise ValueError("Unsupported OS or category.")
        return await self.db.get_random(os_name, category, previous_id)
