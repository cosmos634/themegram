"""Admin-only theme management and broadcast workflows."""
import asyncio
import logging
import uuid
from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter, TelegramAPIError

from database.supabase import SupabaseError
from handlers.admin_states import AddTheme, EditTheme, Broadcast

router = Router(name="admin")
logger = logging.getLogger(__name__)
PLATFORMS = ("iOS", "Android")
CATEGORIES = ("Dark", "Soft", "Anime", "Boshqa")
PAGE_SIZE = 8


def is_admin(user_id: int, settings) -> bool:
    return bool(settings.admin_id and user_id == settings.admin_id)


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_kb():
    return kb([
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stats")],
        [InlineKeyboardButton(text="📈 Traffic Analytics", callback_data="adm:traffic")],
        [InlineKeyboardButton(text="➕ Mavzu qo‘shish", callback_data="adm:add")],
        [InlineKeyboardButton(text="📚 Mavzularni boshqarish", callback_data="adm:list")],
        [InlineKeyboardButton(text="📢 Barcha foydalanuvchilarga xabar yuborish", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="adm:close")],
    ])


def cancel_kb():
    return kb([[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]])


def is_theme_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme == "https" and parsed.hostname in {"t.me", "www.t.me"} and parsed.path.startswith("/addtheme/") and len(parsed.path.split("/")) >= 3 and bool(parsed.path.split("/")[2])
    except ValueError:
        return False


async def deny_message(message: Message, settings):
    if not is_admin(message.from_user.id, settings):
        await message.answer("⛔ Bu bo‘lim faqat administrator uchun.")
        return True
    if not settings.admin_id:
        await message.answer("⚠️ ADMIN_ID sozlanmagan. Admin panel o‘chirilgan.")
        return True
    return False


async def deny_callback(callback: CallbackQuery, settings):
    if not settings.admin_id or callback.from_user.id != settings.admin_id:
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return True
    return False


@router.message(Command("admin"))
async def admin_command(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings):
        return
    await state.clear()
    await message.answer("🛠 <b>ThemeGram boshqaruv paneli</b>", reply_markup=main_kb())


@router.callback_query(F.data.startswith("adm:"))
async def admin_menu(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings):
        return
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "close":
        await state.clear()
        await callback.message.edit_text("Asosiy menyu yopildi.")
    elif action == "cancel":
        await state.clear()
        await callback.message.edit_text("Amal bekor qilindi.", reply_markup=main_kb())
    elif action == "stats":
        try:
            users = await db.count("users")
            themes = await db.count("themes")
            active = await db.count("themes", active_only=True)
            await callback.message.edit_text(
                f"📊 <b>Statistika</b>\n\n👥 Foydalanuvchilar: <b>{users}</b>\n"
                f"🎨 Jami mavzular: <b>{themes}</b>\n✅ Faol mavzular: <b>{active}</b>",
                reply_markup=main_kb())
        except SupabaseError:
            await callback.message.edit_text("⚠️ Statistikani bazadan olib bo‘lmadi. Qayta urinib ko‘ring.", reply_markup=main_kb())
    elif action == "traffic":
        try:
            analytics = await db.traffic_analytics()
            source_lines = [
                f"• {name.replace('_', ' ').title()}: <b>{count}</b>"
                for name, count in sorted(analytics["sources"].items(), key=lambda item: (-item[1], item[0]))
            ] or ["• Ma’lumot yo‘q"]
            langs = analytics["languages"]
            await callback.message.edit_text(
                "📈 <b>Traffic Analytics</b>\\n\\n"
                f"👥 Jami foydalanuvchilar: <b>{analytics['total']}</b>\\n\\n"
                "<b>Kelish manbalari:</b>\\n" + "\\n".join(source_lines) + "\\n\\n"
                "<b>Til statistikasi:</b>\\n"
                f"🇺🇿 O‘zbekcha: <b>{langs['uz']}</b>\\n"
                f"🇷🇺 Русский: <b>{langs['ru']}</b>\\n"
                f"⏳ Tanlanmagan: <b>{langs['unset']}</b>",
                reply_markup=main_kb()
            )
        except SupabaseError:
            await callback.message.edit_text(
                "⚠️ Traffic statistikasini olib bo‘lmadi. SQL migration bajarilganini tekshiring.",
                reply_markup=main_kb()
            )
    elif action == "add":
        await state.clear()
        await state.set_state(AddTheme.platform)
        await callback.message.edit_text("Platformani tanlang:", reply_markup=kb([
            [InlineKeyboardButton(text=x, callback_data=f"add:platform:{x}") for x in PLATFORMS],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")],
        ]))
    elif action == "list":
        await state.clear()
        await show_filters(callback.message, db)
    elif action == "broadcast":
        await state.clear()
        await state.set_state(Broadcast.message)
        await callback.message.edit_text("📢 Yuboriladigan xabarni (matn, rasm, video va boshqalar) shu chatga yuboring.", reply_markup=cancel_kb())


async def show_filters(message, db, platform=None, category=None, page=0):
    rows = [[InlineKeyboardButton(text=f"Platforma: {platform or 'Barchasi'}", callback_data="filter:platform"),
             InlineKeyboardButton(text=f"Kategoriya: {category or 'Barchasi'}", callback_data="filter:category")]]
    try:
        themes = await db.list_themes(platform=platform, category=category, offset=page * PAGE_SIZE, limit=PAGE_SIZE + 1)
    except SupabaseError:
        await message.answer("⚠️ Mavzularni yuklab bo‘lmadi.")
        return
    has_next = len(themes) > PAGE_SIZE
    themes = themes[:PAGE_SIZE]
    if not themes:
        rows.append([InlineKeyboardButton(text="Mavzu topilmadi", callback_data="noop")])
    for theme in themes:
        rows.append([InlineKeyboardButton(
            text=f"{theme['name'][:32]} · {theme['platform']}/{theme['category']}",
            callback_data=f"theme:view:{theme['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page:{page-1}:{platform or '-'}:{category or '-'}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}", callback_data="noop"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page:{page+1}:{platform or '-'}:{category or '-'}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 Admin menyu", callback_data="adm:cancel")])
    await message.answer("📚 <b>Mavzular ro‘yxati</b> — mavzuni tanlang:", reply_markup=kb(rows))


@router.callback_query(F.data == "filter:platform")
async def filter_platform(callback: CallbackQuery, settings):
    if await deny_callback(callback, settings): return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb([
        [InlineKeyboardButton(text=x, callback_data=f"filter:setos:{x}") for x in PLATFORMS],
        [InlineKeyboardButton(text="Barchasi", callback_data="filter:setos:-")],
    ]))


@router.callback_query(F.data == "filter:category")
async def filter_category(callback: CallbackQuery, settings):
    if await deny_callback(callback, settings): return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=kb([
        [InlineKeyboardButton(text=x, callback_data=f"filter:setcat:{x}") for x in CATEGORIES],
        [InlineKeyboardButton(text="Barchasi", callback_data="filter:setcat:-")],
    ]))


@router.callback_query(F.data.startswith("filter:set"))
async def set_filter(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings): return
    await callback.answer()
    parts = callback.data.split(":")
    kind, value = parts[1], parts[2]
    platform = value if kind == "setos" and value != "-" else None
    category = value if kind == "setcat" and value != "-" else None
    # Preserve the other active filter while changing one dimension.
    current_platform = None
    current_category = None
    if kind == "setos":
        current_platform = platform
    else:
        current_category = category
    await show_filters(callback.message, db, current_platform, current_category, 0)


@router.callback_query(F.data.startswith("page:"))
async def paginate(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings): return
    await callback.answer()
    _, page, platform, category = callback.data.split(":", 3)
    await show_filters(callback.message, db, None if platform == "-" else platform,
                       None if category == "-" else category, int(page))


@router.callback_query(F.data.startswith("theme:view:"))
async def theme_view(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings): return
    await callback.answer()
    theme_id = callback.data.split(":", 2)[2]
    try:
        theme = await db.get_theme(theme_id)
    except SupabaseError:
        theme = None
    if not theme:
        await callback.message.answer("Mavzu topilmadi yoki bazadan o‘qib bo‘lmadi.")
        return
    await callback.message.answer(
        f"🎨 <b>{theme['name']}</b>\nID: <code>{theme['id']}</code>\n"
        f"Platforma: {theme['platform']}\nKategoriya: {theme['category']}\n"
        f"Faol: {'ha' if theme.get('is_active', True) else 'yo‘q'}\n"
        f"URL: {theme['url']}\nTavsif: {theme.get('description') or '—'}",
        reply_markup=kb([
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit:choose:{theme_id}")],
            [InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"delete:ask:{theme_id}")],
            [InlineKeyboardButton(text="🔙 Ro‘yxat", callback_data="adm:list")],
        ]))


@router.callback_query(F.data.startswith("add:platform:"))
async def add_platform(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings): return
    value = callback.data.rsplit(":", 1)[1]
    if value not in PLATFORMS:
        await callback.answer("Noto‘g‘ri platforma", show_alert=True); return
    await state.update_data(platform=value)
    await state.set_state(AddTheme.category)
    await callback.answer()
    await callback.message.edit_text("Kategoriyani tanlang:", reply_markup=kb([
        [InlineKeyboardButton(text=x, callback_data=f"add:category:{x}") for x in CATEGORIES],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")],
    ]))


@router.callback_query(F.data.startswith("add:category:"))
async def add_category(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings): return
    value = callback.data.rsplit(":", 1)[1]
    if value not in CATEGORIES:
        await callback.answer("Noto‘g‘ri kategoriya", show_alert=True); return
    await state.update_data(category=value)
    await state.set_state(AddTheme.name)
    await callback.answer()
    await callback.message.edit_text("Mavzu nomini yuboring:", reply_markup=cancel_kb())


@router.message(AddTheme.name)
async def add_name(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings): return
    value = (message.text or "").strip()
    if not value or len(value) > 100:
        await message.answer("Nom 1–100 belgi bo‘lishi kerak.", reply_markup=cancel_kb()); return
    await state.update_data(name=value)
    await state.set_state(AddTheme.url)
    await message.answer("Telegram theme URL yuboring (https://t.me/addtheme/…):", reply_markup=cancel_kb())


@router.message(AddTheme.url)
async def add_url(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings): return
    value = (message.text or "").strip()
    if not is_theme_url(value):
        await message.answer("URL noto‘g‘ri. https://t.me/addtheme/… formatidagi Telegram havolasini yuboring.", reply_markup=cancel_kb()); return
    await state.update_data(url=value)
    await state.set_state(AddTheme.description)
    await message.answer("Tavsifni yuboring (bo‘sh qoldirish uchun — belgisi yuboring):", reply_markup=cancel_kb())


@router.message(AddTheme.description)
async def add_description(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings): return
    value = (message.text or "").strip()
    if not value or len(value) > 1000:
        await message.answer("Tavsif 1–1000 belgi bo‘lishi kerak. Bo‘sh tavsif uchun — yuboring.", reply_markup=cancel_kb()); return
    data = await state.get_data()
    data["description"] = "" if value == "—" else value
    data["id"] = uuid.uuid4().hex
    data["is_active"] = True
    await state.update_data(**data)
    await state.set_state(AddTheme.confirm)
    await message.answer(
        f"Yangi mavzu qo‘shilsinmi?\n\n<b>{data['name']}</b>\n{data['platform']} / {data['category']}\n"
        f"{data['url']}\n{data['description'] or 'Tavsif yo‘q'}",
        reply_markup=kb([[InlineKeyboardButton(text="✅ Saqlash", callback_data="add:confirm"),
                          InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))


@router.callback_query(F.data == "add:confirm", AddTheme.confirm)
async def add_confirm(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings): return
    data = await state.get_data()
    await callback.answer()
    try:
        await db.add_theme({k: data[k] for k in ("id", "platform", "category", "name", "url", "description", "is_active")})
        await state.clear()
        await callback.message.edit_text("✅ Mavzu Supabase’ga saqlandi.", reply_markup=main_kb())
    except SupabaseError:
        await callback.message.answer("⚠️ Mavzuni saqlab bo‘lmadi. Ma’lumotlar o‘zgartirilmadi yoki tekshirib qayta urinib ko‘ring.")


@router.callback_query(F.data.startswith("edit:choose:"))
async def edit_choose(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings): return
    theme_id = callback.data.split(":", 2)[2]
    theme = await db.get_theme(theme_id)
    await callback.answer()
    if not theme:
        await callback.message.answer("Mavzu topilmadi."); return
    await state.clear()
    await state.update_data(theme_id=theme_id)
    fields = [("platform","Platforma"),("category","Kategoriya"),("name","Nom"),("url","URL"),("description","Tavsif")]
    await callback.message.answer(f"Qaysi maydonni tahrirlaysiz? ({theme['name']})", reply_markup=kb([
        [InlineKeyboardButton(text=label, callback_data=f"edit:field:{key}:{theme_id}")] for key,label in fields
    ] + [[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))


@router.callback_query(F.data.startswith("edit:field:"))
async def edit_field(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings): return
    _, _, field, theme_id = callback.data.split(":", 3)
    if field not in {"platform","category","name","url","description"}:
        await callback.answer("Maydon noto‘g‘ri", show_alert=True); return
    await state.clear()
    await state.update_data(theme_id=theme_id, field=field)
    await state.set_state(EditTheme.value)
    await callback.answer()
    if field == "platform":
        await callback.message.answer("Platformani tanlang:", reply_markup=kb([[InlineKeyboardButton(text=x, callback_data=f"edit:value:{x}") for x in PLATFORMS], [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))
    elif field == "category":
        await callback.message.answer("Kategoriyani tanlang:", reply_markup=kb([[InlineKeyboardButton(text=x, callback_data=f"edit:value:{x}") for x in CATEGORIES], [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))
    else:
        await callback.message.answer("Yangi qiymatni yuboring:", reply_markup=cancel_kb())


def valid_field(field, value):
    if field == "platform": return value in PLATFORMS
    if field == "category": return value in CATEGORIES
    if field == "url": return is_theme_url(value)
    if field == "name": return bool(value) and len(value) <= 100
    return bool(value) and len(value) <= 1000


async def prepare_edit(message, state, value):
    data = await state.get_data()
    field = data.get("field")
    value = value.strip()
    if not valid_field(field, value):
        await message.answer("Qiymat noto‘g‘ri yoki uzunligi ruxsat etilgan chegaradan tashqarida.", reply_markup=cancel_kb()); return
    await state.update_data(new_value=value)
    await state.set_state(EditTheme.confirm)
    await message.answer(f"<b>{field}</b> maydoni quyidagiga o‘zgartirilsinmi?\n{value}",
        reply_markup=kb([[InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="edit:confirm"),
                          InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))


@router.callback_query(F.data.startswith("edit:value:"), EditTheme.value)
async def edit_value_callback(callback: CallbackQuery, settings, state: FSMContext):
    if await deny_callback(callback, settings): return
    await callback.answer()
    await prepare_edit(callback.message, state, callback.data.rsplit(":", 1)[1])


@router.message(EditTheme.value)
async def edit_value_message(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings): return
    await prepare_edit(message, state, message.text or "")


@router.callback_query(F.data == "edit:confirm", EditTheme.confirm)
async def edit_confirm(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings): return
    data = await state.get_data()
    await callback.answer()
    try:
        await db.update_theme(data["theme_id"], {data["field"]: data["new_value"]})
        await state.clear()
        await callback.message.edit_text("✅ O‘zgarish Supabase’da saqlandi va qayta tekshirildi.", reply_markup=main_kb())
    except SupabaseError:
        await callback.message.answer("⚠️ Tahrirlash bajarilmadi. Bazadan tasdiq olinmadi.")


@router.callback_query(F.data.startswith("delete:ask:"))
async def delete_ask(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings): return
    theme_id = callback.data.split(":", 2)[2]
    theme = await db.get_theme(theme_id)
    await callback.answer()
    if not theme:
        await callback.message.answer("Mavzu topilmadi."); return
    await callback.message.answer(f"🗑 <b>{theme['name']}</b> o‘chirilsinmi?",
        reply_markup=kb([[InlineKeyboardButton(text="✅ Ha, o‘chirish", callback_data=f"delete:yes:{theme_id}"),
                          InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))


@router.callback_query(F.data.startswith("delete:yes:"))
async def delete_confirm(callback: CallbackQuery, settings, db):
    if await deny_callback(callback, settings): return
    theme_id = callback.data.split(":", 2)[2]
    await callback.answer()
    try:
        deleted = await db.delete_theme(theme_id)
        await callback.message.answer("✅ Mavzu o‘chirildi." if deleted else "Mavzu topilmadi yoki o‘chmadi.", reply_markup=main_kb())
    except SupabaseError:
        await callback.message.answer("⚠️ Mavzuni o‘chirib bo‘lmadi.")


@router.message(Broadcast.message)
async def broadcast_preview(message: Message, settings, state: FSMContext):
    if await deny_message(message, settings): return
    await state.update_data(source_chat_id=message.chat.id, source_message_id=message.message_id)
    await state.set_state(Broadcast.confirm)
    try:
        await message.bot.copy_message(chat_id=message.chat.id, from_chat_id=message.chat.id,
                                       message_id=message.message_id)
    except TelegramAPIError:
        pass
    await message.answer("Ushbu xabar barcha foydalanuvchilarga yuborilsinmi?",
        reply_markup=kb([[InlineKeyboardButton(text="✅ Barchaga yuborish", callback_data="broadcast:send"),
                          InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm:cancel")]]))


@router.callback_query(F.data == "broadcast:send", Broadcast.confirm)
async def broadcast_send(callback: CallbackQuery, settings, db, state: FSMContext):
    if await deny_callback(callback, settings): return
    data = await state.get_data()
    await state.clear()
    await callback.answer("Yuborish boshlandi.")
    try:
        ids = await db.user_ids()
    except SupabaseError:
        await callback.message.answer("⚠️ Foydalanuvchilar ro‘yxatini bazadan olib bo‘lmadi.")
        return
    await callback.message.answer(f"📢 Yuborish boshlandi: {len(ids)} foydalanuvchi.")
    success = failed = 0
    for user_id in ids:
        while True:
            try:
                await callback.bot.copy_message(chat_id=user_id, from_chat_id=data["source_chat_id"],
                                                message_id=data["source_message_id"])
                success += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except (TelegramForbiddenError, TelegramBadRequest):
                failed += 1
                break
            except TelegramAPIError:
                failed += 1
                break
            except Exception:
                failed += 1
                logger.exception("Broadcast delivery failed for a user")
                break
        await asyncio.sleep(0.05)
    await callback.message.answer(f"✅ <b>Tarqatish yakunlandi</b>\nJami: {len(ids)}\nYuborildi: {success}\nYuborilmadi: {failed}", reply_markup=main_kb())


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery, settings):
    if await deny_callback(callback, settings): return
    await callback.answer()
