import asyncio
import logging
from asyncio import Task

from aiogram import Bot
from aiogram.enums import InputMediaType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import URLInputFile, InputFile, InputMediaPhoto
from aiogram.utils.media_group import MediaGroupBuilder

from database.database_connector import GroupPair, DatabaseConnector, MessageStatusEnum, get_next_msg, \
    get_all_matching_media


class SenderTaskManager:
    def __init__(self, db: DatabaseConnector, bot: Bot):
        self.tasks: dict[int, Task] = {}
        self.db = db
        self.bot = bot

    def add_task(self, group_pair: GroupPair):
        self.tasks[group_pair.private_chat_id] = asyncio.create_task(self._sender_task(group_pair.private_chat_id),
                                                                     name=str(group_pair.private_chat_id))

    def update_interval(self, group_pair: GroupPair):
        self.tasks[group_pair.private_chat_id].cancel()
        self.tasks[group_pair.private_chat_id] = asyncio.create_task(self._sender_task(group_pair.private_chat_id),
                                                                     name=str(group_pair.private_chat_id))

    async def _sender_task(self, private_chat_id: int):
        while True:
            logging.debug("Getting next msg")
            async with self.db.session_factory.begin() as session:
                group_pair = await session.get(GroupPair, private_chat_id)
                if group_pair is None:
                    logging.fatal(f"No group pair in the database for {private_chat_id=}, quiting this task")
                    return
                # noinspection PyTypeChecker
                next_msg = await get_next_msg(session, group_pair)
                logging.debug(f"Next msg is {next_msg}")
                if next_msg is None:
                    await asyncio.sleep(group_pair.interval)
                    continue

                logging.debug("Sending...")

                try:
                    if next_msg.media_group_id:
                        # noinspection PyTypeChecker
                        msg_media_group = await get_all_matching_media(session, next_msg.media_group_id)
                        media_list = []
                        for msg in msg_media_group:
                            single_media = InputMediaPhoto(media=msg.file_ids)
                            if msg.text:
                                single_media.caption = msg.text
                            media_list.append(single_media)
                        sent_msgs = await self.bot.send_media_group(group_pair.public_chat_id,
                                                                    media=media_list)
                        sent_msg = sent_msgs[0]
                        # hack
                        for msg in msg_media_group:
                            msg.status = MessageStatusEnum.SENT

                            try:
                                await self.bot.delete_message(msg.group_pair_id,
                                                              msg.message_id)
                            except TelegramAPIError:
                                logging.exception("Exception while trying to delete message:")
                    elif next_msg.file_ids:
                        # noinspection PyTypeChecker
                        sent_msg = await self.bot.send_photo(group_pair.public_chat_id, next_msg.file_ids,
                                                             caption=next_msg.text, request_timeout=20)
                    elif next_msg.links:
                        # noinspection PyTypeChecker
                        sent_msg = await self.bot.send_photo(group_pair.public_chat_id,
                                                             URLInputFile(url=next_msg.links),
                                                             caption=next_msg.text, request_timeout=20)
                    elif next_msg.text:
                        # noinspection PyTypeChecker
                        sent_msg = await self.bot.send_message(group_pair.public_chat_id,
                                                               text=next_msg.text, request_timeout=20)

                    logging.debug(f"{sent_msg=}")
                    next_msg.status = MessageStatusEnum.SENT
                except TelegramAPIError:
                    logging.warning("Exception while trying to resend message:")
                    next_msg.status = MessageStatusEnum.ERROR

                try:
                    await self.bot.delete_message(next_msg.group_pair_id,
                                                  next_msg.message_id)
                except TelegramAPIError:
                    logging.exception("Exception while trying to delete message:")

            await asyncio.sleep(group_pair.interval)
