import logging
from html import escape
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from database.supabase import SupabaseError
from keyboards.inline import (
    os_keyboard, categories_keyboard, theme_keyboard, OS_LABELS, CATEGORY_LABELS
)

router = Router(name="themes")
logger = logging.getLogger(__name__)


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
    try:
        state = await db.get_state(callback.from_user.id)
    except SupabaseError:
        await safe_edit(callback, "⚠️ Bazaga ulanib bo‘lmadi. Keyinroq qayta urinib ko‘ring.")
        return
    if not state or state.get("selected_os") not in OS_LABELS:
        await safe_edit(callback, "📱 <b>Avval operatsion tizimni tanlang:</b>", os_keyboard())
        return
    os_name = state["selected_os"]
    await safe_edit(callback,
                    f"{OS_LABELS[os_name]} tanlandi.\n\n🎨 <b>Kerakli tema kategoriyasini tanlang:</b>",
                    categories_keyboard(include_os_button))


async def show_theme(callback, db, themes, os_name, category, previous_id=None):
    try:
        theme = await themes.get_random(os_name, category, previous_id)
        if theme is None:
            await safe_edit(callback,
                f"😕 <b>{escape(CATEGORY_LABELS[category])}</b> kategoriyasida hozircha temalar yo‘q.\n"
                "Keyinroq qayta urinib ko‘ring.",
                categories_keyboard(include_os_button=True))
            return
        await db.set_theme(callback.from_user.id, theme["id"])
    except SupabaseError:
        await safe_edit(callback, "⚠️ Temalarni bazadan yuklab bo‘lmadi. Keyinroq qayta urinib ko‘ring.")
        return
    text = f"🎨 <b>{escape(theme['name'])}</b>\n"
    description = theme.get("description")
    if description and description.strip():
        text += f"\n{escape(description.strip())}\n"
    text += "\n📥 <i>Temani ochish uchun «O‘rnatish» tugmasini bosing.</i>"
    await safe_edit(callback, text, theme_keyboard(theme["url"]))


@router.callback_query(F.data.startswith("os:"))
async def choose_os(callback: CallbackQuery, db):
    os_name = callback.data.partition(":")[2]
    if os_name not in OS_LABELS:
        await callback.answer("Noto‘g‘ri tanlov.", show_alert=True)
        return
    await callback.answer()
    try:
        await db.set_os(callback.from_user.id, os_name)
    except SupabaseError:
        await safe_edit(callback, "⚠️ Tanlovni saqlab bo‘lmadi. Keyinroq urinib ko‘ring.")
        return
    await show_categories(callback, db)


@router.callback_query(F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, db, themes):
    category = callback.data.partition(":")[2]
    if category not in CATEGORY_LABELS:
        await callback.answer("Noto‘g‘ri kategoriya.", show_alert=True)
        return
    await callback.answer()
    try:
        state = await db.get_state(callback.from_user.id)
        if not state or state.get("selected_os") not in OS_LABELS:
            await safe_edit(callback, "📱 <b>Avval operatsion tizimni tanlang:</b>", os_keyboard())
            return
        await db.set_category(callback.from_user.id, category)
        await show_theme(callback, db, themes, state["selected_os"], category)
    except SupabaseError:
        await safe_edit(callback, "⚠️ Tanlovni saqlab bo‘lmadi. Qaytadan urinib ko‘ring.")


@router.callback_query(F.data == "theme:next")
async def next_theme(callback: CallbackQuery, db, themes):
    await callback.answer()
    try:
        state = await db.get_state(callback.from_user.id)
    except SupabaseError:
        await safe_edit(callback, "⚠️ Bazaga ulanib bo‘lmadi. Keyinroq urinib ko‘ring.")
        return
    if not state or state.get("selected_os") not in OS_LABELS or state.get("selected_category") not in CATEGORY_LABELS:
        await safe_edit(callback, "⌛ Tanlov muddati tugagan. Qaytadan boshlang:", os_keyboard())
        return
    await show_theme(callback, db, themes, state["selected_os"], state["selected_category"],
                     previous_id=state.get("current_theme_id"))


@router.callback_query(F.data == "nav:categories")
async def back_to_categories(callback: CallbackQuery, db):
    await callback.answer()
    await show_categories(callback, db, include_os_button=True)


@router.callback_query(F.data == "nav:os")
async def back_to_os(callback: CallbackQuery):
    await callback.answer()
    await safe_edit(callback, "📱 <b>Telefoningiz qaysi operatsion tizimda ishlaydi?</b>", os_keyboard())
