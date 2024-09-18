import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from database.database_connector import get_db, DatabaseConnector, get_all_pairs
from middlewares.session_middleware import DBSessionMiddleware
from middlewares.updates_dumper_middleware import UpdatesDumperMiddleware
from resender_bot.commands import set_bot_commands
from resender_bot.handlers.base_handlers import router as base_router
from resender_bot.handlers.errors_handler import router as errors_router
from resender_bot.logging_config import setup_logs
from resender_bot.notify_admin import on_shutdown_notify, on_startup_notify
from resender_bot.sender_task import SenderTaskManager
from resender_bot.settings import Settings


async def recreate_tasks(task_manager: SenderTaskManager, db: DatabaseConnector):
    async with db.session_factory.begin() as db_session:
        pairs = await get_all_pairs(db_session)
    for pair in pairs:
        logging.debug(f"Adding pair {pair}")
        task_manager.add_task(pair)


async def main():
    setup_logs()

    settings = Settings()

    session = AiohttpSession(timeout=120)

    bot = Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )

    logging.info("bot started")
    storage = MemoryStorage()
    db = get_db(settings)
    await db.create_all()

    task_manager = SenderTaskManager(db, bot, settings.ADMIN_ID)
    dispatcher = Dispatcher(storage=storage, task_manager=task_manager, settings=settings)

    db_session_middleware = DBSessionMiddleware(db)
    dispatcher.message.middleware(db_session_middleware)
    dispatcher.edited_message.middleware(db_session_middleware)
    dispatcher.callback_query.middleware(db_session_middleware)
    dispatcher.update.outer_middleware(UpdatesDumperMiddleware())
    dispatcher.startup.register(on_startup_notify)
    dispatcher.shutdown.register(on_shutdown_notify)
    dispatcher.startup.register(set_bot_commands)
    dispatcher.include_routers(
        base_router,
        errors_router,
    )

    await recreate_tasks(task_manager, db)

    await dispatcher.start_polling(bot)


def run_main():
    asyncio.run(main())


if __name__ == '__main__':
    run_main()
