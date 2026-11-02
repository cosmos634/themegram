import logging
import re
from html import escape
from io import BytesIO
from urllib.parse import unquote

import aiohttp
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message

from locales import t

router = Router(name="attheme")
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
API_TIMEOUT_SECONDS = 60
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class AtthemeFlow(StatesGroup):
    waiting_for_image = State()


def language_for(db, user_id: int) -> str:
    return db.get_language(user_id) or "uz"


def theme_name_for(message: Message) -> str:
    first_name = (message.from_user.first_name or "ThemeGram").strip()
    safe_name = re.sub(r"[\\/:*?\"<>|\x00-\x1f\x7f]+", "", first_name)
    safe_name = re.sub(r"\s+", "_", safe_name).strip("._-")[:48] or "ThemeGram"
    return f"ThemeGram_{safe_name}"


async def get_image_from_message(message: Message) -> tuple[bytes, str]:
    telegram_file = None
    filename = "wallpaper.jpg"

    if message.photo:
        telegram_file = await message.bot.get_file(message.photo[-1].file_id)
    elif message.document:
        document = message.document
        mime = (document.mime_type or "").lower()
        name = (document.file_name or "").lower()
        if mime not in ALLOWED_MIME_TYPES and not name.endswith(ALLOWED_EXTENSIONS):
            raise ValueError("attheme_image_invalid")
        if document.file_size and document.file_size > MAX_IMAGE_BYTES:
            raise ValueError("attheme_image_too_large")
        telegram_file = await message.bot.get_file(document.file_id)
        filename = document.file_name or "wallpaper"
    else:
        raise ValueError("attheme_image_invalid")

    if telegram_file.file_size and telegram_file.file_size > MAX_IMAGE_BYTES:
        raise ValueError("attheme_image_too_large")

    buffer = BytesIO()
    await message.bot.download_file(telegram_file.file_path, destination=buffer)
    image_bytes = buffer.getvalue()
    if not image_bytes:
        raise ValueError("attheme_image_invalid")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("attheme_image_too_large")
    return image_bytes, filename


def response_filename(content_disposition: str | None, fallback: str) -> str:
    if content_disposition:
        match = re.search(
            r"filename\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE
        )
        if match:
            filename = unquote(match.group(1)).strip().strip('"')
            if filename.lower().endswith(".attheme"):
                return filename
    return f"{fallback}.attheme"


async def request_attheme(
    image_bytes: bytes,
    image_filename: str,
    theme_name: str,
    api_url: str,
    api_key: str,
) -> tuple[bytes, str]:
    form = aiohttp.FormData()
    form.add_field(
        "image",
        image_bytes,
        filename=image_filename,
        content_type="application/octet-stream",
    )
    form.add_field("theme_name", theme_name)
    timeout = aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS, connect=10, sock_read=50)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{api_url.rstrip('/')}/api/v1/generate",
            headers={"X-API-Key": api_key},
            data=form,
        ) as response:
            if response.status != 200:
                error_key = {
                    401: "attheme_api_401",
                    413: "attheme_api_413",
                    422: "attheme_api_422",
                    429: "attheme_api_429",
                }.get(response.status, "attheme_api_error")
                raise RuntimeError(error_key)
            theme_bytes = await response.read()
            if not theme_bytes:
                raise RuntimeError("attheme_api_error")
            filename = response_filename(
                response.headers.get("Content-Disposition"), theme_name
            )
            return theme_bytes, filename


@router.message(F.text.in_({"✨ Tema yaratish", "✨ Создать тему"}))
async def start_attheme_flow(message: Message, state: FSMContext, db, settings):
    language = language_for(db, message.from_user.id)
    await state.clear()
    if not settings.attheme_api_url or not settings.attheme_api_key:
        await message.answer(t(language, "attheme_api_unconfigured"))
        return
    await state.set_state(AtthemeFlow.waiting_for_image)
    await message.answer(t(language, "attheme_intro"))


@router.message(Command("cancel"))
async def cancel_attheme_flow(message: Message, state: FSMContext, db):
    if await state.get_state() != AtthemeFlow.waiting_for_image.state:
        return
    language = language_for(db, message.from_user.id)
    await state.clear()
    await message.answer(t(language, "attheme_cancelled"))


@router.message(AtthemeFlow.waiting_for_image, F.photo | F.document)
async def create_attheme_from_image(message: Message, state: FSMContext, db, settings):
    language = language_for(db, message.from_user.id)
    try:
        image_bytes, image_filename = await get_image_from_message(message)
    except ValueError as exc:
        await message.answer(t(language, str(exc)))
        return
    except Exception:
        logger.exception("Telegram image download failed")
        await message.answer(t(language, "attheme_api_error"))
        return

    theme_name = theme_name_for(message)
    status = await message.answer(t(language, "attheme_processing"))
    try:
        theme_bytes, output_filename = await request_attheme(
            image_bytes=image_bytes,
            image_filename=image_filename,
            theme_name=theme_name,
            api_url=settings.attheme_api_url,
            api_key=settings.attheme_api_key,
        )
        await status.edit_text(t(language, "attheme_file_ready"))
        await message.answer_document(
            BufferedInputFile(theme_bytes, filename=output_filename),
            caption=t(language, "attheme_ready", theme_name=escape(theme_name)),
        )
    except RuntimeError as exc:
        await status.edit_text(t(language, str(exc)))
    except (aiohttp.ClientError, TimeoutError):
        logger.exception("Attheme API connection failed")
        await status.edit_text(t(language, "attheme_api_connection"))
    except Exception:
        logger.exception("Unexpected attheme generation error")
        await status.edit_text(t(language, "attheme_api_error"))
    finally:
        await state.clear()


@router.message(AtthemeFlow.waiting_for_image)
async def waiting_for_attheme_image(message: Message, db):
    language = language_for(db, message.from_user.id)
    await message.answer(t(language, "attheme_image_invalid"))
