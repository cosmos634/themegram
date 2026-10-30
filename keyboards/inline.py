from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from locales import t

OS_LABELS = {"iOS": "🍎 iOS", "Android": "🤖 Android"}
CATEGORY_KEYS = {"Dark": "category_dark", "Soft": "category_soft", "Anime": "category_anime", "Boshqa": "category_other"}
CATEGORY_LABELS = {"Dark": "🌑 Dark", "Soft": "☁️ Soft", "Anime": "🎌 Anime", "Boshqa": "✨ Boshqa"}


def os_keyboard(language: str = "uz"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=OS_LABELS["iOS"], callback_data="os:iOS"),
        InlineKeyboardButton(text=OS_LABELS["Android"], callback_data="os:Android"),
    ]])


def categories_keyboard(include_os_button: bool = False, language: str = "uz"):
    rows = [
        [InlineKeyboardButton(text=t(language, CATEGORY_KEYS["Dark"]), callback_data="cat:Dark"),
         InlineKeyboardButton(text=t(language, CATEGORY_KEYS["Soft"]), callback_data="cat:Soft")],
        [InlineKeyboardButton(text=t(language, CATEGORY_KEYS["Anime"]), callback_data="cat:Anime"),
         InlineKeyboardButton(text=t(language, CATEGORY_KEYS["Boshqa"]), callback_data="cat:Boshqa")],
    ]
    if include_os_button:
        rows.append([InlineKeyboardButton(text=t(language, "os_button"), callback_data="nav:os")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def theme_keyboard(url: str, language: str = "uz"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "install"), url=url),
         InlineKeyboardButton(text=t(language, "next"), callback_data="theme:next")],
        [InlineKeyboardButton(text=t(language, "home"), callback_data="nav:categories")],
    ])
