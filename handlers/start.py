from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.reply import main_reply_keyboard
from keyboards.inline import os_keyboard
from database.supabase import SupabaseError

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(message: Message, db):
    try:
        await db.touch(message.from_user)
    except SupabaseError:
        await message.answer("⚠️ Ma’lumotlar bazasiga ulanib bo‘lmadi. Iltimos, birozdan keyin qayta urinib ko‘ring.")
        return
    text = (
        "👋 <b>ThemeGram’ga xush kelibsiz!</b>\n\n"
        "📱 <b>iOS va Android</b> uchun temalarni toping.\n"
        "🎨 <b>Foydalanish:</b> «Temalar»ni bosing, operatsion tizim va kategoriyani tanlang. "
        "«O‘rnatish» temaga olib boradi, «Keyingi» esa boshqa temani ko‘rsatadi.\n\n"
        "Boshlash uchun quyidagi menyudan foydalaning 👇"
    )
    await message.answer(text, reply_markup=main_reply_keyboard())


@router.message(F.text == "🎨 Temalar")
async def themes_entry(message: Message, db):
    try:
        await db.touch(message.from_user)
    except SupabaseError:
        await message.answer("⚠️ Bazaga ulanib bo‘lmadi. Keyinroq qayta urinib ko‘ring.")
        return
    await message.answer("📱 <b>Telefoningiz qaysi operatsion tizimda ishlaydi?</b>",
                         reply_markup=os_keyboard())


@router.message(F.text == "📢 Kanalga a’zo bo‘lish")
async def channel_entry(message: Message, settings, db):
    try:
        await db.touch(message.from_user)
    except SupabaseError:
        await message.answer("⚠️ Bazaga ulanib bo‘lmadi. Keyinroq qayta urinib ko‘ring.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📢 Kanalni ochish", url=settings.channel_url)
    ]])
    await message.answer("📢 <b>Rasmiy kanalimiz:</b>", reply_markup=keyboard)
