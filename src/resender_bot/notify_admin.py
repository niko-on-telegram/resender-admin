import os

from aiogram import Bot

from resender_bot.settings import Settings


async def on_startup_notify(bot: Bot, settings: Settings):
    folder = os.path.basename(os.getcwd())
    await bot.send_message(
        settings.ADMIN_ID,
        f'<b>{folder.replace("_", " ")} started</b>\n\n/start',
        disable_notification=True,
    )


async def on_shutdown_notify(bot: Bot, settings: Settings):
    folder = os.path.basename(os.getcwd())
    await bot.send_message(
        settings.ADMIN_ID,
        f'<b>{folder.replace("_", " ")} shutdown</b>',
        disable_notification=True,
    )
