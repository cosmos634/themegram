from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from locales import t


def main_reply_keyboard(language: str = "uz") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(language, "menu_themes")),
                KeyboardButton(text=t(language, "menu_favorites")),
            ],
            [
                KeyboardButton(text=t(language, "menu_channel")),
                KeyboardButton(text=t(language, "menu_language")),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder=t(language, "input_placeholder"),
    )


def language_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🇺🇿 O‘zbekcha"), KeyboardButton(text="🇷🇺 Русский")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
