"""ThemeGram application entry point: Telegram webhook + health endpoint."""
import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import BASE_DIR, load_settings
from database.db import UserStateDB
from handlers.start import router as start_router
from handlers.themes import router as themes_router
from services.cleanup import cleanup_loop
from services.theme_service import ThemeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("themegram")


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def main() -> None:
    settings = load_settings()
    db = UserStateDB(settings.database_path)
    await db.initialize()

    themes = ThemeService(BASE_DIR / "data" / "themes.json")
    themes.load()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(themes_router)
    dispatcher["db"] = db
    dispatcher["settings"] = settings
    dispatcher["themes"] = themes

    cleanup_task = asyncio.create_task(cleanup_loop(db), name="themegram-state-cleanup")
    app = web.Application()
    app.router.add_get("/health", health)
    webhook_url = settings.webhook_base_url + settings.webhook_path
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)
    setup_application(app, dispatcher, bot=bot)

    runner = web.AppRunner(app)
    try:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=settings.port)
        await site.start()
        logger.info("ThemeGram webhook server started on port %s", settings.port)
        await asyncio.Event().wait()
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.exception("Could not delete webhook during shutdown")
        await runner.cleanup()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError) as exc:
        logger.error("Startup failed: %s", exc)
        raise
