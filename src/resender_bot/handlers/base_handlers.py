from aiogram import Router, F
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.database_connector import GroupPair, SendOrderEnum

router = Router()


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start(message: Message) -> None:
    await message.answer('Hello!\n' 'This bot works in groups only.')


@router.message(CommandStart(), F.chat.type != ChatType.PRIVATE)
async def start(message: Message) -> None:
    start_message = '\n'.join(
        [
            "Hello!",
            "Here's a list of supported commands:",
            "/register <channel id> - bind this group to a channel",
            "(bot must be admin in both)\n",
            "/set_random - sets order of sending to be random",
            "/set_ordered - sets order of sending to be the same as they were sent",
            "/set_interval <seconds> - set delay before messages in seconds",
            "/info - get info about settings for current chat",
        ]
    )
    await message.answer(start_message)


@router.message(Command('register'), F.chat.type != ChatType.PRIVATE)
async def setup_command_group(
    message: Message, command: CommandObject, db_session: AsyncSession
):
    private_chat_id = message.chat.id

    try:
        public_chat_id = int(command.args)
    except ValueError:
        await message.answer("/register requires integer as parameter")
        return

    new_pair = GroupPair(public_chat_id=public_chat_id, private_chat_id=private_chat_id)
    db_session.add(new_pair)
    await message.answer(f"Registered successfully!")


@router.message(Command('set_random'), F.chat.type != ChatType.PRIVATE)
async def setup_command_group(message: Message, db_session: AsyncSession):
    private_chat_id = message.chat.id

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    chat_pair.send_order = SendOrderEnum.RANDOM
    await message.answer(f"Order is set to Random!")


@router.message(Command('set_ordered'), F.chat.type != ChatType.PRIVATE)
async def setup_command_group(message: Message, db_session: AsyncSession):
    private_chat_id = message.chat.id

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    chat_pair.send_order = SendOrderEnum.OLDEST
    await message.answer(f"Order is set to Ordered!")


@router.message(Command('set_interval'), F.chat.type != ChatType.PRIVATE)
async def setup_command_group(
    message: Message, command: CommandObject, db_session: AsyncSession
):
    private_chat_id = message.chat.id

    try:
        interval = int(command.args)
    except ValueError:
        await message.answer("/set_interval requires integer as parameter")
        return

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    chat_pair.interval = interval
    await message.answer(f"Interval is set to {interval}!")


@router.message(Command('info'), F.chat.type != ChatType.PRIVATE)
async def setup_command_group(message: Message, db_session: AsyncSession):
    private_chat_id = message.chat.id

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    await message.answer(
        "Chat Info:\n"
        f"├ Channel id: {chat_pair.public_chat_id}\n"
        f"├ This group id: {chat_pair.private_chat_id}\n"
        f"├ Send order: {chat_pair.send_order}\n"
        f"└ Interval: {chat_pair.interval}\n"
    )
