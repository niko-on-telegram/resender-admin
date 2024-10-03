from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, select, and_, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from resender_bot.settings import Settings


class SendOrderEnum(StrEnum):
    RANDOM = "RANDOM"
    OLDEST = "OLDEST"


class MessageStatusEnum(StrEnum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    ERROR = "ERROR"


class Base(DeclarativeBase):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(UTC)
    )


class GroupPair(Base):
    __tablename__ = 'group_pairs'

    public_chat_id: Mapped[int] = mapped_column(BigInteger)
    private_chat_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    send_order: Mapped[SendOrderEnum] = mapped_column(default=SendOrderEnum.OLDEST)
    interval: Mapped[int] = mapped_column(default=180)

    def __str__(self):
        return f"GroupPair(public_chat_id={self.public_chat_id}, private_chat_id={self.private_chat_id}, send_order={self.send_order}, interval={self.interval})"


class ScheduledMessage(Base):
    __tablename__ = 'scheduled_messages'

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int]
    group_pair_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[MessageStatusEnum] = mapped_column(default=MessageStatusEnum.NOT_SENT)
    text: Mapped[str | None]
    links: Mapped[str | None]
    file_id: Mapped[str | None]
    media_group_id: Mapped[str | None]
    media_type: Mapped[str | None]
    meta_info: Mapped[str]

    def __str__(self):
        return (
            f"ScheduledMessage(id={self.id}, message_id={self.message_id}, group_pair_id={self.group_pair_id},"
            f"status={self.status} text={self.text} links={self.links} file_ids={self.file_id})"
        )


async def get_next_msg(
    session: AsyncSession, group_pair: GroupPair
) -> ScheduledMessage | None:
    query = (
        select(ScheduledMessage)
        .where(
            and_(
                ScheduledMessage.group_pair_id == group_pair.private_chat_id,
                ScheduledMessage.status == MessageStatusEnum.NOT_SENT,
            )
        )
        .limit(1)
    )
    if group_pair.send_order == SendOrderEnum.OLDEST:
        query = query.order_by(ScheduledMessage.created_at)
    elif group_pair.send_order == SendOrderEnum.RANDOM:
        query = query.order_by(func.random())
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_all_pairs(db_session: AsyncSession) -> list[GroupPair]:
    query = select(GroupPair)
    result = await db_session.execute(query)
    return list(result.scalars())


async def get_all_matching_media(
    db_session: AsyncSession, media_group_id: str
) -> list[ScheduledMessage]:
    query = select(ScheduledMessage).where(
        ScheduledMessage.media_group_id == media_group_id
    )
    result = await db_session.execute(query)
    return list(result.scalars())


async def get_scheduled_message(
    db_session: AsyncSession, message_id: int, group_id: int
) -> ScheduledMessage:
    query = (
        select(ScheduledMessage)
        .where(
            and_(
                ScheduledMessage.message_id == message_id,
                ScheduledMessage.group_pair_id == group_id,
            )
        )
        .limit(1)
    )
    result = await db_session.execute(query)
    return result.scalar_one_or_none()


async def upsert_new_group_pair(
    db_session: AsyncSession, private_chat_id: int, public_channel_id: int
):
    query = (
        insert(GroupPair)
        .values(private_chat_id=private_chat_id, public_chat_id=public_channel_id)
        .on_conflict_do_update(
            index_elements=[GroupPair.private_chat_id],
            set_={GroupPair.public_chat_id: public_channel_id},
        )
    )

    result = await db_session.execute(query)
    return result.rowcount


class DatabaseConnector:
    def __init__(
        self,
        url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url=url,
            echo=False,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def create_all(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


def get_db(settings: Settings) -> DatabaseConnector:
    return DatabaseConnector(url=settings.DB_URL.get_secret_value())
