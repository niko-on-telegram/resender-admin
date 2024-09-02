from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllChatAdministrators


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(
                command="register",
                description="/register <channel id> - bind this group to a channel",
            ),
            BotCommand(
                command="set_random", description="sets order of sending to be random",
            ),
            BotCommand(
                command="set_ordered",
                description="sets order of sending to be the same as they were sent",
            ),
            BotCommand(
                command="set_interval",
                description="/set_interval <seconds> - set delay before messages in seconds",
            ),
            BotCommand(
                command="info", description="get info about settings for current chat",
            ),
        ],
        scope=BotCommandScopeAllChatAdministrators(),
    )
