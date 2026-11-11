"""Admin CRUD for Telegram language-pack links."""
from html import escape
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.supabase import SupabaseError
from handlers.admin_states import AddLanguage, EditLanguage

router = Router(name="admin_languages")


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def is_admin(user_id: int, settings) -> bool:
    return bool(settings.admin_id and user_id == settings.admin_id)


def valid_language_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme == "https"
            and parsed.hostname in {"t.me", "www.t.me"}
            and parsed.path.startswith("/setlanguage/")
            and bool(parsed.path.split("/")[2])
        )
    except (ValueError, IndexError):
        return False


async def deny_message(message: Message, settings) -> bool:
    if not is_admin(message.from_user.id, settings):
        await message.answer("⛔ Bu bo‘lim faqat administrator uchun.")
        return True
    return False


async def deny_callback(callback: CallbackQuery, settings) -> bool:
    if not is_admin(callback.from_user.id, settings):
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return True
    return False


def menu_keyboard():
    return kb([
        [InlineKeyboardButton(text="➕ Til havolasi qo‘shish", callback_data="langadm:add")],
        [InlineKeyboardButton(text="📚 Til havolalarini ko‘rish", callback_data="langadm:list")],
        [InlineKeyboardButton(text="🔙 Admin menyu", callback_data="adm:cancel")],
    ])


async def show_language_list(message, db):
    items = await db.list_languages()
    rows = [
        [InlineKeyboardButton(text=f"🌐 {item['name'][:45]}",
                              callback_data=f"langadm:view:{item['id']}")]
        for item in items
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Hozircha til yo‘q", callback_data="langadm:menu")]]
    rows.append([InlineKeyboardButton(text="➕ Yangi til", callback_data="langadm:add")])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="langadm:menu")])
    await message.edit_text("🌐 <b>Telegram til paketlari</b>", reply_markup=kb(rows))


@router.callback_query(F.data == "langadm:menu")
async def language_admin_menu(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings):
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("🌐 <b>Til havolalarini boshqarish</b>", reply_markup=menu_keyboard())


@router.callback_query(F.data == "langadm:add")
async def language_add_start(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings):
        return
    await state.clear()
    await state.set_state(AddLanguage.name)
    await callback.answer()
    await callback.message.edit_text("Yangi til paketining nomini yuboring:", reply_markup=kb([
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]
    ]))


@router.message(AddLanguage.name)
async def language_add_name(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 80:
        await message.answer("Til nomi 1–80 belgi bo‘lishi kerak.")
        return
    await state.update_data(name=name)
    await state.set_state(AddLanguage.url)
    await message.answer("Telegram til paketi havolasini yuboring (https://t.me/setlanguage/…):")


@router.message(AddLanguage.url)
async def language_add_url(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings):
        return
    url = (message.text or "").strip()
    if not valid_language_url(url):
        await message.answer("Havola noto‘g‘ri. https://t.me/setlanguage/… formatidan foydalaning.")
        return
    await state.update_data(url=url)
    data = await state.get_data()
    await state.set_state(AddLanguage.confirm)
    await message.answer(
        f"Quyidagi til paketini saqlaymizmi?\n\n<b>{escape(data['name'])}</b>\n{escape(url)}",
        reply_markup=kb([
            [InlineKeyboardButton(text="✅ Saqlash", callback_data="langadm:add:save")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")],
        ])
    )


@router.callback_query(F.data == "langadm:add:save", AddLanguage.confirm)
async def language_add_save(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings):
        return
    data = await state.get_data()
    try:
        item = await db.add_language_pack(data["name"], data["url"])
        await state.clear()
        await callback.answer("Saqlandi.")
        await callback.message.edit_text(
            f"✅ <b>{escape(item['name'])}</b> til paketi Supabase’ga qo‘shildi.",
            reply_markup=menu_keyboard()
        )
    except SupabaseError:
        await callback.answer("Bazaga saqlab bo‘lmadi.", show_alert=True)


@router.callback_query(F.data == "langadm:list")
async def language_admin_list(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings):
        return
    await callback.answer()
    try:
        await show_language_list(callback.message, db)
    except SupabaseError:
        await callback.message.answer("⚠️ Til paketlarini yuklab bo‘lmadi.")


@router.callback_query(F.data.startswith("langadm:view:"))
async def language_admin_view(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings):
        return
    language_id = callback.data.split(":", 2)[2]
    try:
        item = await db.get_language_pack(language_id)
    except SupabaseError:
        item = None
    await callback.answer()
    if not item:
        await callback.message.answer("Til paketi topilmadi.")
        return
    await callback.message.edit_text(
        f"🌐 <b>{escape(item['name'])}</b>\n{escape(item['url'])}",
        reply_markup=kb([
            [InlineKeyboardButton(text="✏️ Nomini o‘zgartirish", callback_data=f"langadm:edit:name:{language_id}")],
            [InlineKeyboardButton(text="🔗 Havolani o‘zgartirish", callback_data=f"langadm:edit:url:{language_id}")],
            [InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"langadm:delete:ask:{language_id}")],
            [InlineKeyboardButton(text="🔙 Ro‘yxat", callback_data="langadm:list")],
        ])
    )


@router.callback_query(F.data.startswith("langadm:edit:"))
async def language_edit_start(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings):
        return
    parts = callback.data.split(":")
    if len(parts) != 4 or parts[2] not in {"name", "url"}:
        await callback.answer("Noto‘g‘ri maydon.", show_alert=True)
        return
    _, _, field, language_id = parts
    await state.clear()
    await state.update_data(language_id=language_id, field=field)
    await state.set_state(EditLanguage.value)
    await callback.answer()
    await callback.message.answer(
        "Yangi til nomini yuboring:" if field == "name" else "Yangi Telegram til havolasini yuboring:"
    )


@router.message(EditLanguage.value)
async def language_edit_value(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings):
        return
    data = await state.get_data()
    value = (message.text or "").strip()
    valid = bool(value) and len(value) <= (80 if data["field"] == "name" else 500)
    if data["field"] == "url":
        valid = valid and valid_language_url(value)
    if not valid:
        await message.answer("Qiymat noto‘g‘ri. Qayta yuboring.")
        return
    await state.update_data(new_value=value)
    await state.set_state(EditLanguage.confirm)
    await message.answer(
        f"Maydon o‘zgartirilsinmi?\n\n<b>{data['field']}</b>: {escape(value)}",
        reply_markup=kb([
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="langadm:edit:save")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")],
        ])
    )


@router.callback_query(F.data == "langadm:edit:save", EditLanguage.confirm)
async def language_edit_save(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings):
        return
    data = await state.get_data()
    try:
        await db.update_language_pack(data["language_id"], {data["field"]: data["new_value"]})
        await state.clear()
        await callback.answer("Yangilandi.")
        await callback.message.edit_text("✅ Til paketi yangilandi.", reply_markup=menu_keyboard())
    except SupabaseError:
        await callback.answer("O‘zgarishni saqlab bo‘lmadi.", show_alert=True)


@router.callback_query(F.data.startswith("langadm:delete:ask:"))
async def language_delete_ask(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings):
        return
    language_id = callback.data.split(":", 3)[3]
    item = await db.get_language_pack(language_id)
    await callback.answer()
    if not item:
        await callback.message.answer("Til paketi topilmadi.")
        return
    await callback.message.edit_text(
        f"🗑 <b>{escape(item['name'])}</b> o‘chirilsinmi?",
        reply_markup=kb([
            [InlineKeyboardButton(text="✅ Ha, o‘chirish", callback_data=f"langadm:delete:yes:{language_id}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"langadm:view:{language_id}")],
        ])
    )


@router.callback_query(F.data.startswith("langadm:delete:yes:"))
async def language_delete_confirm(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings):
        return
    language_id = callback.data.split(":", 3)[3]
    try:
        deleted = await db.delete_language_pack(language_id)
        await callback.answer("O‘chirildi." if deleted else "Til topilmadi.")
        await callback.message.edit_text("🗑 Til paketi o‘chirildi." if deleted else "Til paketi topilmadi.",
                                         reply_markup=menu_keyboard())
    except SupabaseError:
        await callback.answer("O‘chirib bo‘lmadi.", show_alert=True)
