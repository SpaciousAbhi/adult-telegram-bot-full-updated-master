from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import ConfigError, get_settings
from app.database import Database, MongoStartupError
from app.middleware import AppContextMiddleware
from app.routers import register_routers
from app.services.legacy_postgres import import_legacy_postgres_users
from app.services.task_runner import TaskScheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        settings = get_settings()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    db = Database(settings)
    try:
        await db.connect()
    except MongoStartupError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc
    await import_legacy_postgres_users(db, settings.legacy_database_url)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    scheduler = TaskScheduler(db, settings, bot)
    middleware = AppContextMiddleware(db, settings, scheduler)
    dp.update.middleware(middleware)
    register_routers(dp)

    await bot.delete_webhook(drop_pending_updates=False)
    await scheduler.start()
    logger.info("Bot worker started")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "callback_query",
                "chat_join_request",
                "chat_member",
            ],
        )
    finally:
        await scheduler.stop()
        await bot.session.close()
        db.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
