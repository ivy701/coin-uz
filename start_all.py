#!/usr/bin/env python
"""Start both Telegram bot and aiohttp API server."""
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_api_server():
    from aiohttp import web
    from api.server import create_app
    from bot.config import settings

    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or 8080)
    host = os.environ.get("API_HOST", "0.0.0.0")

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("API server listening on %s:%s", host, port)
    return runner


async def run_bot():
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.fsm.storage.memory import MemoryStorage
    import config
    import database
    from handlers import start, shop, balance, profile, webapp, admin

    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(webapp.router)
    dp.include_router(shop.router)
    dp.include_router(balance.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)

    await database.init_db()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"delete_webhook notice: {e}")
    logger.info("Bot starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def main():
    runner = await run_api_server()
    try:
        await run_bot()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
