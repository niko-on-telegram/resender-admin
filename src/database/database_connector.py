from datetime import UTC, datetime
from enum import StrEnum

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


class Base(DeclarativeBase):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(default=datetime.now(UTC))


class GroupPair(Base):
    __tablename__ = 'group_pairs'

    public_chat_id: Mapped[int]
    private_chat_id: Mapped[int] = mapped_column(
        primary_key=True,
    )  # autoincrement = False
    send_order: Mapped[SendOrderEnum] = mapped_column(default=SendOrderEnum.OLDEST)
    interval: Mapped[int] = mapped_column(default=180)


class ScheduledMessage(Base):
    __tablename__ = 'shedules_messages'

    message_id: Mapped[int]
    group_pair_id: Mapped[int]
    status: Mapped[MessageStatusEnum] = mapped_column(default=MessageStatusEnum.NOT_SENT)


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
