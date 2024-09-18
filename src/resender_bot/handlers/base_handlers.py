import asyncio
import logging

import aiogram
from aiogram import F, Router, Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.database_connector import GroupPair, SendOrderEnum, ScheduledMessage, get_all_pairs, get_scheduled_message
from resender_bot.sender_task import SenderTaskManager

router = Router()


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start_private_handler(message: Message) -> None:
    await message.answer('Hello!\nThis bot works in groups only.')


@router.message(CommandStart(), F.chat.type != ChatType.PRIVATE)
async def start_group_handler(message: Message) -> None:
    start_message = '\n\n'.join(
        [
            "Hello!",
            "Here's a list of supported commands:",
            aiogram.html.quote("/register <channel id> - bind this group to a channel"),
            "(bot must be admin in both)\n",
            "/set_random - sets order of sending to be random",
            "/set_ordered - sets order of sending to be the same as they were sent",
            aiogram.html.quote(
                "/set_interval <seconds> - set delay before messages in seconds"
            ),
            "/info - get info about settings for current chat",
        ],
    )
    await message.answer(start_message)


async def is_bot_admin(bot: Bot,
                       channel_id: int) -> bool:
    try:
        chat_administrators = await bot.get_chat_administrators(channel_id)
        return any(admin.user.id == bot.id for admin in chat_administrators)
    except TelegramAPIError:
        logging.exception(f"Error checking if bot is admin")
        return False


@router.message(Command('register'), F.chat.type != ChatType.PRIVATE)
async def register_handler(
        message: Message,
        bot: Bot,
        command: CommandObject,
        db_session: AsyncSession,
        task_manager: SenderTaskManager
):
    private_chat_id = message.chat.id

    try:
        channel_id_str = command.args
        if not channel_id_str.startswith("-100"):
            channel_id_str = "-100" + channel_id_str
        channel_id = int(channel_id_str)
    except (ValueError, TypeError, AttributeError):
        await message.answer("/register requires integer as parameter")
        return

    if not await is_bot_admin(bot, channel_id):
        await message.answer("Bot must be an administrator in the registered channel")
        return

    new_pair = GroupPair(public_chat_id=channel_id, private_chat_id=private_chat_id)
    db_session.add(new_pair)
    task_manager.add_task(new_pair)
    await message.answer("Registered successfully!")


@router.message(Command('set_random'), F.chat.type != ChatType.PRIVATE)
async def set_random_handler(message: Message, db_session: AsyncSession):
    private_chat_id = message.chat.id

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    chat_pair.send_order = SendOrderEnum.RANDOM
    await message.answer("Order is set to Random!")


@router.message(Command('set_ordered'), F.chat.type != ChatType.PRIVATE)
async def set_ordered_handler(message: Message, db_session: AsyncSession):
    private_chat_id = message.chat.id

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    chat_pair.send_order = SendOrderEnum.OLDEST
    await message.answer("Order is set to Ordered!")


@router.message(Command('set_interval'), F.chat.type != ChatType.PRIVATE)
async def set_interval_handler(
        message: Message,
        command: CommandObject,
        db_session: AsyncSession,
        task_manager: SenderTaskManager

):
    private_chat_id = message.chat.id

    try:
        interval = int(command.args)
    except (ValueError, TypeError):
        await message.answer("/set_interval requires integer as parameter")
        return

    chat_pair = await db_session.get(GroupPair, private_chat_id)
    if chat_pair is None:
        await message.answer("This chat wasn't registered yet")
        return

    chat_pair.interval = interval
    # noinspection PyTypeChecker
    task_manager.update_interval(chat_pair)
    await message.answer(f"Interval is set to {interval}!")


@router.message(Command('info'), F.chat.type != ChatType.PRIVATE)
async def info_handler(message: Message, db_session: AsyncSession):
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
        f"└ Interval: {chat_pair.interval}\n",
    )


async def in_src(chat_id: int, db_session: AsyncSession):
    pairs = await get_all_pairs(db_session)
    src_ids = [pair.private_chat_id for pair in pairs]
    return chat_id in src_ids


def extract_text(text: str, entities):
    if entities is None:
        return text, []
    message_cleared_text = ""
    encoded_text = text.encode("utf-16-le")
    last_offset = 0
    links = []
    for ent in entities:
        if ent.type != "url":
            continue
        encoded_link = encoded_text[ent.offset * 2: (ent.offset + ent.length) * 2]
        decoded_text_piece = encoded_text[last_offset:ent.offset * 2].decode('utf-16-le')
        message_cleared_text += decoded_text_piece
        last_offset = (ent.offset + ent.length) * 2
        link = encoded_link.decode("utf-16-le")
        links.append(link)

    message_cleared_text += encoded_text[last_offset:].decode('utf-16-le')
    return message_cleared_text, links


def extract_info(message: Message):
    message_cleared_str = None
    links = []
    if message.text:
        message_cleared_str, links = extract_text(message.text, message.entities)
    if message.caption:
        message_cleared_str, links = extract_text(message.caption, message.caption_entities)
    links_str = ';'.join(links) or None
    file_id = message.photo[-1].file_id if message.photo else None
    return message_cleared_str, links_str, file_id


@router.message()
async def any_message(message: Message, db_session: AsyncSession):
    if not await in_src(message.chat.id, db_session):
        return

    logging.info(f"Adding new message: {message.text=}")

    message_cleared_str, links_str, file_id = extract_info(message)

    scheduled_msg = ScheduledMessage(message_id=message.message_id,
                                     group_pair_id=message.chat.id,
                                     text=message_cleared_str,
                                     links=links_str,
                                     file_id=file_id,
                                     media_group_id=message.media_group_id)

    db_session.add(scheduled_msg)
    msg = await message.answer("Scheduled successfully")
    # hack
    await db_session.commit()
    await asyncio.sleep(5)
    await msg.delete()


@router.edited_message()
async def any_edit_message(message: Message, db_session: AsyncSession):
    if not await in_src(message.chat.id, db_session):
        return

    logging.info(f"Editing existing message: {message.text=}")

    message_cleared_str, links_str, file_id = extract_info(message)

    scheduled_msg = await get_scheduled_message(db_session, message.message_id,
                                                message.chat.id)
    scheduled_msg.text = message_cleared_str
    scheduled_msg.links = links_str
    scheduled_msg.file_id = file_id

    logging.info("Updated successfully")
