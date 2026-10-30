import logging
from html import escape
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from database.supabase import SupabaseError
from keyboards.inline import (
    os_keyboard, categories_keyboard, theme_keyboard, OS_LABELS, CATEGORY_LABELS
)
from locales import t

router = Router(name="themes")
logger = logging.getLogger(__name__)


def language_for(db, user_id: int) -> str:
    return db.get_language(user_id) or "uz"


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None):
    if not callback.message:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        logger.info("Message edit failed; sending fallback message.")
        await callback.message.answer(text, reply_markup=reply_markup)


async def show_categories(callback: CallbackQuery, db, include_os_button=False):
    language = language_for(db, callback.from_user.id)
    try:
        state = await db.get_state(callback.from_user.id)
    except SupabaseError:
        await safe_edit(callback, t(language, "db_failed"))
        return
    if not state or state.get("selected_os") not in OS_LABELS:
        await safe_edit(callback, t(language, "os_prompt"), os_keyboard(language))
        return
    os_name = state["selected_os"]
    await safe_edit(
        callback, t(language, "os_selected", os=OS_LABELS[os_name]),
        categories_keyboard(include_os_button, language)
    )


async def show_theme(callback, db, themes, os_name, category, previous_id=None):
    language = language_for(db, callback.from_user.id)
    try:
        theme = await themes.get_random(os_name, category, previous_id)
        if theme is None:
            await safe_edit(
                callback, t(language, "category_empty", category=CATEGORY_LABELS[category]),
                categories_keyboard(include_os_button=True, language=language)
            )
            return
        await db.set_theme(callback.from_user.id, theme["id"])
    except SupabaseError:
        await safe_edit(callback, t(language, "themes_failed"))
        return
    # Theme names/descriptions are creator-provided content; preserve their original text.
    text = f"🎨 <b>{escape(theme['name'])}</b>\n"
    description = theme.get("description")
    if description and description.strip():
        text += f"\n{escape(description.strip())}\n"
    text += "\n" + t(language, "install_hint")
    await safe_edit(callback, text, theme_keyboard(theme["url"], language))


@router.callback_query(F.data.startswith("os:"))
async def choose_os(callback: CallbackQuery, db):
    language = language_for(db, callback.from_user.id)
    os_name = callback.data.partition(":")[2]
    if os_name not in OS_LABELS:
        await callback.answer(t(language, "invalid_choice"), show_alert=True)
        return
    await callback.answer()
    try:
        await db.set_os(callback.from_user.id, os_name)
    except SupabaseError:
        await safe_edit(callback, t(language, "save_failed"))
        return
    await show_categories(callback, db)


@router.callback_query(F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, db, themes):
    language = language_for(db, callback.from_user.id)
    category = callback.data.partition(":")[2]
    if category not in CATEGORY_LABELS:
        await callback.answer(t(language, "invalid_category"), show_alert=True)
        return
    await callback.answer()
    try:
        state = await db.get_state(callback.from_user.id)
        if not state or state.get("selected_os") not in OS_LABELS:
            await safe_edit(callback, t(language, "os_prompt"), os_keyboard(language))
            return
        await db.set_category(callback.from_user.id, category)
        await show_theme(callback, db, themes, state["selected_os"], category)
    except SupabaseError:
        await safe_edit(callback, t(language, "save_failed"))


@router.callback_query(F.data == "theme:next")
async def next_theme(callback: CallbackQuery, db, themes):
    language = language_for(db, callback.from_user.id)
    await callback.answer()
    try:
        state = await db.get_state(callback.from_user.id)
    except SupabaseError:
        await safe_edit(callback, t(language, "db_failed"))
        return
    if not state or state.get("selected_os") not in OS_LABELS or state.get("selected_category") not in CATEGORY_LABELS:
        await safe_edit(callback, t(language, "theme_not_found"), os_keyboard(language))
        return
    await show_theme(
        callback, db, themes, state["selected_os"], state["selected_category"],
        previous_id=state.get("current_theme_id")
    )


@router.callback_query(F.data == "nav:categories")
async def back_to_categories(callback: CallbackQuery, db):
    await callback.answer()
    await show_categories(callback, db, include_os_button=True)


@router.callback_query(F.data == "nav:os")
async def back_to_os(callback: CallbackQuery, db):
    await callback.answer()
    language = language_for(db, callback.from_user.id)
    await safe_edit(callback, t(language, "os_prompt"), os_keyboard(language))
