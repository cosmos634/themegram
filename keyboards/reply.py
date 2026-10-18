from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎨 Temalar"), KeyboardButton(text="📢 Kanalga a’zo bo‘lish")]],
        resize_keyboard=True,
        input_field_placeholder="Bo‘limni tanlang…",
    )
