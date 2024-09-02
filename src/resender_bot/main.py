import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from database.database_connector import get_db
from middlewares.session_middleware import DBSessionMiddleware
from middlewares.updates_dumper_middleware import UpdatesDumperMiddleware
from resender_bot.commands import set_bot_commands
from resender_bot.handlers.base_handlers import router as base_router
from resender_bot.handlers.errors_handler import router as errors_router
from resender_bot.logging_config import setup_logs
from resender_bot.notify_admin import on_shutdown_notify, on_startup_notify
from resender_bot.settings import Settings


async def main():
    setup_logs()

    settings = Settings()

    bot = Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    logging.info("bot started")
    storage = MemoryStorage()
    db = get_db(settings)
    await db.create_all()
    tasks = []
    dispatcher = Dispatcher(
        storage=storage,
        tasks=tasks,
    )

    db_session_middleware = DBSessionMiddleware(db)
    dispatcher.message.middleware(db_session_middleware)
    dispatcher.callback_query.middleware(db_session_middleware)
    dispatcher.update.outer_middleware(UpdatesDumperMiddleware())
    dispatcher.startup.register(on_startup_notify)
    dispatcher.shutdown.register(on_shutdown_notify)
    dispatcher.startup.register(set_bot_commands)
    dispatcher.include_routers(
        base_router,
        errors_router,
    )

    await dispatcher.start_polling(bot)


def run_main():
    asyncio.run(main())


if __name__ == '__main__':
    run_main()
