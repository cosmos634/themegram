"""User-facing Telegram language catalogue."""
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest

from database.supabase import SupabaseError
from locales import t

router = Router(name="languages")
LANGUAGE_MENU_BUTTONS = {"🌐 Telegram tillari", "🌐 Языки Telegram"}


def language_for(db, user_id: int) -> str:
    return db.get_language(user_id) or "uz"


def language_card_keyboard(language: str, item: dict, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(language, "language_install"),
                              callback_data=f"lang:install:{item['id']}")],
        [
            InlineKeyboardButton(text=t(language, "language_back"),
                                 callback_data=f"lang:prev:{index}"),
            InlineKeyboardButton(text=t(language, "language_next"),
                                 callback_data=f"lang:next:{index}"),
        ],
    ])


async def render_language_card(target, db, language: str, index: int, *, edit: bool = False):
    items = await db.list_languages()
    if not items:
        text = t(language, "languages_empty")
        if edit:
            try:
                await target.message.edit_text(text)
            except TelegramBadRequest:
                await target.message.answer(text)
        else:
            await target.answer(text)
        return
    index %= len(items)
    item = items[index]
    await db.track_event(target.from_user.id, "language_viewed", {"language_id": str(item["id"])})
    text = (
        t(language, "languages_title") + "\n"
        f"<b>{escape(str(item['name']))}</b>\n\n"
        + t(language, "language_card_hint")
        + f"\n\n<code>{escape(str(index + 1))}/{len(items)}</code>"
    )
    markup = language_card_keyboard(language, item, index)
    if edit:
        try:
            await target.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                await target.message.answer(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text.in_(LANGUAGE_MENU_BUTTONS))
async def languages_entry(message: Message, db):
    language = language_for(db, message.from_user.id)
    try:
        await db.touch(message.from_user, first_source="unknown")
        await render_language_card(message, db, language, 0)
    except SupabaseError:
        await message.answer(t(language, "db_failed"))


@router.callback_query(F.data.regexp(r"^lang:(next|prev):\\d+$"))
async def language_navigation(callback: CallbackQuery, db):
    language = language_for(db, callback.from_user.id)
    _, action, raw_index = callback.data.split(":")
    index = int(raw_index)
    try:
        items = await db.list_languages()
        if not items:
            await callback.answer(t(language, "languages_empty"), show_alert=True)
            return
        new_index = (index + (1 if action == "next" else -1)) % len(items)
        await callback.answer()
        await render_language_card(callback, db, language, new_index, edit=True)
    except SupabaseError:
        await callback.answer(t(language, "db_failed"), show_alert=True)


@router.callback_query(F.data.startswith("lang:install:"))
async def language_install(callback: CallbackQuery, db):
    language = language_for(db, callback.from_user.id)
    language_id = callback.data.split(":", 2)[2]
    try:
        item = await db.get_language_pack(language_id)
        if not item:
            await callback.answer(t(language, "language_not_found"), show_alert=True)
            return
        await db.track_event(callback.from_user.id, "language_install_clicked",
                             {"language_id": str(item["id"])})
        await callback.answer()
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(language, "language_open"), url=item["url"])
        ]])
        await callback.message.answer(t(language, "language_open_hint"), reply_markup=markup)
    except SupabaseError:
        await callback.answer(t(language, "db_failed"), show_alert=True)
