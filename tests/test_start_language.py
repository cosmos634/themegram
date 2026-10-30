import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from database.local_cache import LocalStateCache
from database.supabase import SupabaseDB
from handlers.start import start_handler, choose_language


class StartLanguageFlowTests(unittest.IsolatedAsyncioTestCase):
    def make_message(self, text=None):
        return SimpleNamespace(
            text=text,
            from_user=SimpleNamespace(id=77),
            answer=AsyncMock(),
        )

    async def test_first_start_prompts_for_language_and_captures_source(self):
        message = self.make_message("/start instagram")
        db = SimpleNamespace(
            touch=AsyncMock(), get_language=lambda user_id: None
        )
        command = SimpleNamespace(args="instagram")
        await start_handler(message, db, command)
        db.touch.assert_awaited_once_with(message.from_user, first_source="instagram")
        self.assertIn("Tilni tanlang", message.answer.await_args.args[0])

    async def test_saved_russian_language_is_reused_on_start(self):
        message = self.make_message("/start")
        db = SimpleNamespace(
            touch=AsyncMock(), get_language=lambda user_id: "ru"
        )
        await start_handler(message, db, SimpleNamespace(args=None))
        self.assertIn("Добро пожаловать", message.answer.await_args.args[0])

    async def test_language_choice_updates_profile_and_menu(self):
        message = self.make_message("🇷🇺 Русский")
        db = SimpleNamespace(set_language=AsyncMock())
        await choose_language(message, db)
        db.set_language.assert_awaited_once_with(77, "ru")
        self.assertIn("Язык изменён", message.answer.await_args_list[0].args[0])
        self.assertIn("Добро пожаловать", message.answer.await_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
