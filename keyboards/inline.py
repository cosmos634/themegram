from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

OS_LABELS = {"iOS": "🍎 iOS", "Android": "🤖 Android"}
CATEGORY_LABELS = {"Dark": "🌑 Dark", "Soft": "☁️ Soft", "Anime": "🎌 Anime", "Boshqa": "✨ Boshqa"}


def os_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=OS_LABELS["iOS"], callback_data="os:iOS"),
        InlineKeyboardButton(text=OS_LABELS["Android"], callback_data="os:Android"),
    ]])


def categories_keyboard(include_os_button: bool = False):
    rows = [
        [InlineKeyboardButton(text=CATEGORY_LABELS["Dark"], callback_data="cat:Dark"),
         InlineKeyboardButton(text=CATEGORY_LABELS["Soft"], callback_data="cat:Soft")],
        [InlineKeyboardButton(text=CATEGORY_LABELS["Anime"], callback_data="cat:Anime"),
         InlineKeyboardButton(text=CATEGORY_LABELS["Boshqa"], callback_data="cat:Boshqa")],
    ]
    if include_os_button:
        rows.append([InlineKeyboardButton(text="🔄 OS tanlash", callback_data="nav:os")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def theme_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 O‘rnatish", url=url),
         InlineKeyboardButton(text="➡️ Keyingi", callback_data="theme:next")],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:categories")],
    ])
