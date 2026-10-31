from aiogram import Router, F
from html import escape
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.reply import main_reply_keyboard, language_keyboard
from keyboards.inline import os_keyboard
from database.supabase import SupabaseError
from locales import t
from services.traffic import parse_start_source

router = Router(name="start")
LANGUAGE_BUTTONS = {"🇺🇿 O‘zbekcha": "uz", "🇷🇺 Русский": "ru"}


async def show_welcome(message: Message, language: str):
    await message.answer(t(language, "welcome"), reply_markup=main_reply_keyboard(language))


@router.message(CommandStart())
async def start_handler(message: Message, db, command: CommandObject):
    source = parse_start_source(command.args)
    try:
        await db.touch(message.from_user, first_source=source)
    except SupabaseError:
        await message.answer(t("uz", "db_start_failed"))
        return
    await db.track_event(message.from_user.id, "bot_started", {"source": source})
    language = db.get_language(message.from_user.id)
    if language not in {"uz", "ru"}:
        await message.answer(t("uz", "choose_language"), reply_markup=language_keyboard())
        return
    await show_welcome(message, language)


@router.message(F.text.in_(set(LANGUAGE_BUTTONS)))
async def choose_language(message: Message, db):
    language = LANGUAGE_BUTTONS[message.text]
    try:
        await db.set_language(message.from_user.id, language)
    except (SupabaseError, KeyError):
        await message.answer(t(language, "save_failed"))
        return
    await message.answer(t(language, "language_saved"), reply_markup=main_reply_keyboard(language))
    await show_welcome(message, language)


@router.message(F.text.in_({"🌐 Tilni o‘zgartirish", "🌐 Изменить язык"}))
async def change_language(message: Message, db):
    try:
        await db.touch(message.from_user, first_source="unknown")
    except SupabaseError:
        await message.answer(t("uz", "db_failed"))
        return
    language = db.get_language(message.from_user.id) or "uz"
    await message.answer(t(language, "choose_language"), reply_markup=language_keyboard())


@router.message(F.text.in_({"🎨 Temalar", "🎨 Темы"}))
async def themes_entry(message: Message, db):
    language = db.get_language(message.from_user.id) or "uz"
    try:
        await db.touch(message.from_user, first_source="unknown")
    except SupabaseError:
        await message.answer(t(language, "db_failed"))
        return
    await message.answer(t(language, "os_prompt"), reply_markup=os_keyboard(language))


@router.message(F.text.in_({"📢 Kanalga a’zo bo‘lish", "📢 Подписаться на канал"}))
async def channel_entry(message: Message, settings, db):
    language = db.get_language(message.from_user.id) or "uz"
    try:
        await db.touch(message.from_user, first_source="unknown")
    except SupabaseError:
        await message.answer(t(language, "db_failed"))
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(language, "channel_open"), url=settings.channel_url)
    ]])
    await message.answer(t(language, "channel_title"), reply_markup=keyboard)


@router.message(F.text.in_({"⭐ Sevimlilar", "⭐ Избранное"}))
async def favorites_entry(message: Message, db):
    language = db.get_language(message.from_user.id) or "uz"
    try:
        favorites = await db.list_favorites(message.from_user.id)
    except SupabaseError:
        await message.answer(t(language, "db_failed"))
        return
    if not favorites:
        await message.answer(t(language, "favorites_empty"))
        return
    lines = [t(language, "favorites_title")]
    for theme in favorites[:30]:
        lines.append(
            f"• <b>{escape(str(theme['name']))}</b> — "
            f"{escape(str(theme['platform']))} / {escape(str(theme['category']))}\n"
            f"{escape(str(theme['url']))}"
        )
    await message.answer("\n\n".join(lines), disable_web_page_preview=True)


@router.message(Command("search"))
async def search_themes_handler(message: Message, db):
    language = db.get_language(message.from_user.id) or "uz"
    query = (message.text or "").partition(" ")[2].strip()
    if not query:
        await message.answer(
            "🔎 Qidirish uchun: /search tema nomi"
            if language == "uz" else "🔎 Для поиска: /search название темы"
        )
        return
    try:
        results = await db.search_themes(query, limit=10)
    except SupabaseError:
        await message.answer(t(language, "db_failed"))
        return
    await db.track_event(message.from_user.id, "theme_search", {"query_length": min(len(query), 80)})
    if not results:
        await message.answer(
            "🔎 Mos tema topilmadi." if language == "uz" else "🔎 Подходящие темы не найдены."
        )
        return
    lines = ["🔎 <b>Qidiruv natijalari</b>"]
    for theme in results:
        lines.append(
            f"• <b>{escape(str(theme['name']))}</b> — "
            f"{escape(str(theme['platform']))} / {escape(str(theme['category']))}\n"
            f"{escape(str(theme['url']))}"
        )
    lines[0] = (
        "🔎 <b>Qidiruv natijalari</b>"
        if language == "uz" else "🔎 <b>Результаты поиска</b>"
    )
    await message.answer("\n\n".join(lines), disable_web_page_preview=True)
