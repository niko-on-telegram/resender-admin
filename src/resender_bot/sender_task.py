import asyncio
import logging
import traceback
from asyncio import Task

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import URLInputFile, InputMediaPhoto, InputMediaVideo

from database.database_connector import (
    GroupPair,
    DatabaseConnector,
    MessageStatusEnum,
    get_next_msg,
    get_all_matching_media,
)


async def get_mime(link: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(link) as r:
            return r.content_type.split('/')[0]


class SenderTaskManager:
    def __init__(self, db: DatabaseConnector, bot: Bot, admin_id: int):
        self.tasks: dict[int, Task] = {}
        self.db = db
        self.bot = bot
        self.admin_id = admin_id
        self.events: dict[int, asyncio.Event] = {}

    def add_task(self, group_pair: GroupPair):
        self.tasks[group_pair.private_chat_id] = asyncio.create_task(
            self._sender_task(group_pair.private_chat_id),
            name=str(group_pair.private_chat_id),
        )
        self.events[group_pair.private_chat_id] = asyncio.Event()

    def update_interval(self, group_pair: GroupPair):
        self.events[group_pair.private_chat_id].set()

    async def _process_single_msg(self, private_chat_id: int):
        logging.debug(f"{private_chat_id=}: Getting next msg")
        event = self.events[private_chat_id]
        async with self.db.session_factory.begin() as session:
            group_pair = await session.get(GroupPair, private_chat_id)
            if group_pair is None:
                raise RuntimeError(f"{private_chat_id=}: No group pair in the database for {private_chat_id=}, quiting this task")
            # noinspection PyTypeChecker
            next_msg = await get_next_msg(session, group_pair)
            logging.debug(f"{private_chat_id=}: Next msg is {next_msg}")
            if next_msg is None:
                await asyncio.wait_for(event.wait(), timeout=group_pair.interval)
                return

            logging.debug(f"{private_chat_id=}: Sending...")

            sent_msg = None

            try:
                if next_msg.media_group_id:
                    # noinspection PyTypeChecker
                    msg_media_group = await get_all_matching_media(
                        session, next_msg.media_group_id
                    )
                    media_list = []
                    for msg in msg_media_group:
                        single_media = InputMediaPhoto(media=msg.file_id)
                        if msg.text:
                            single_media.caption = msg.text
                        media_list.append(single_media)
                    sent_msgs = await self.bot.send_media_group(
                        group_pair.public_chat_id, media=media_list
                    )
                    sent_msg = sent_msgs[0]
                    # hack
                    for msg in msg_media_group:
                        msg.status = MessageStatusEnum.SENT

                        try:
                            await self.bot.delete_message(
                                msg.group_pair_id, msg.message_id
                            )
                        except TelegramAPIError:
                            logging.exception(
                                f"{private_chat_id=}: Exception while trying to delete message:"
                            )
                elif next_msg.file_id:
                    # noinspection PyTypeChecker
                    sent_msg = await self.bot.send_photo(
                        group_pair.public_chat_id,
                        next_msg.file_id,
                        caption=next_msg.text,
                        request_timeout=20,
                    )
                elif next_msg.links:
                    splited_links = next_msg.links.split(';')
                    if len(splited_links) == 1:
                        mime = await get_mime(splited_links[0])
                        if mime == 'image':
                            # noinspection PyTypeChecker
                            sent_msg = await self.bot.send_photo(
                                group_pair.public_chat_id,
                                URLInputFile(url=splited_links[0]),
                                caption=next_msg.text
                            )
                        elif mime == 'video':
                            # noinspection PyTypeChecker
                            sent_msg = await self.bot.send_video(
                                group_pair.public_chat_id,
                                URLInputFile(url=splited_links[0]),
                                caption=next_msg.text,
                                request_timeout=90
                            )
                    else:
                        media_list = []
                        for link in splited_links:
                            mime = await get_mime(link)
                            if mime == 'image':
                                single_media = InputMediaPhoto(media=URLInputFile(url=link))
                            elif mime == 'video':
                                single_media = InputMediaVideo(media=URLInputFile(url=link))
                            media_list.append(single_media)
                        media_list[0].caption = next_msg.text
                        sent_msgs = await self.bot.send_media_group(group_pair.public_chat_id,
                                                                    media=media_list,
                                                                    request_timeout=90)
                        sent_msg = sent_msgs[0]
                elif next_msg.text:
                    # noinspection PyTypeChecker
                    sent_msg = await self.bot.send_message(
                        group_pair.public_chat_id,
                        text=next_msg.text,
                        request_timeout=20,
                    )

                if sent_msg is not None:
                    logging.debug(f"{private_chat_id=}: {sent_msg=}")
                else:
                    logging.error(f"{private_chat_id=}: Sent msg is None for some reason")
                    await self.bot.send_message(self.admin_id, f"{private_chat_id=}: Sent msg is None for some reason")
                next_msg.status = MessageStatusEnum.SENT
            except TelegramAPIError:
                logging.exception(f"{private_chat_id=}: Exception while trying to resend message:")
                next_msg.status = MessageStatusEnum.ERROR

            try:
                await self.bot.delete_message(
                    next_msg.group_pair_id, next_msg.message_id
                )
            except TelegramAPIError:
                logging.exception(f"{private_chat_id=}: Exception while trying to delete message:")

        await asyncio.wait_for(event.wait(), timeout=group_pair.interval)

    async def _sender_task(self, private_chat_id: int):
        while True:
            try:
                self.events[private_chat_id].clear()
                await self._process_single_msg(private_chat_id)
            except TimeoutError:
                pass
            except Exception as e:
                logging.exception("Unexpected thing happened:")

                exc_traceback = ''.join(
                    traceback.format_exception(None, e, e.__traceback__),
                )
                tb = exc_traceback[-3500:]

                error_message = (
                    f"🚨 <b>An error occurred</b> 🚨\n\n"
                    f"<b>Type:</b> {type(e).__name__}\n<b>Message:</b> {e}\n\n<b>Traceback:</b>\n<code>{tb}</code>"
                )

                await self.bot.send_message(self.admin_id, error_message)
