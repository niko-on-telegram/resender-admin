import asyncio
import logging
from asyncio import Task

from aiogram import Bot

from database.database_connector import GroupPair, DatabaseConnector, MessageStatusEnum


class SenderTaskManager:
    def __init__(self, db: DatabaseConnector, bot: Bot):
        self.tasks: dict[int, Task] = {}
        self.db = db
        self.bot = bot

    def add_task(self, group_pair: GroupPair):
        self.tasks[group_pair.private_chat_id] = asyncio.create_task(self._sender_task(group_pair),
                                                                     name=str(group_pair.private_chat_id))

    def update_interval(self, group_pair: GroupPair):
        self.tasks[group_pair.private_chat_id].cancel()
        self.tasks[group_pair.private_chat_id] = asyncio.create_task(self._sender_task(group_pair),
                                                                     name=str(group_pair.private_chat_id))

    async def _sender_task(self, group_pair: GroupPair):
        while True:
            logging.debug("Getting next msg")
            async with self.db.session_factory.begin() as session:
                next_msg = await self.db.get_next_msg(session, group_pair.private_chat_id)
                logging.debug(f"Next msg is {next_msg}")
                if next_msg is None:
                    await asyncio.sleep(group_pair.interval)
                    continue
                logging.debug("Sending...")

                # public = int(str(group_pair.public_chat_id).removeprefix('-100'))
                # private = int(str(group_pair.private_chat_id).removeprefix('-100'))

                sent_msg = await self.bot.copy_message(group_pair.public_chat_id, group_pair.private_chat_id,
                                                       next_msg.message_id)
                logging.debug(f"{sent_msg=}")
                next_msg.status = MessageStatusEnum.SENT

            await asyncio.sleep(group_pair.interval)
