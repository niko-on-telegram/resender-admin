import pytest

from database.database_connector import upsert_new_group_pair, GroupPair


@pytest.mark.asyncio
async def test_upsert_new_group_pair(db):
    async with db.session_factory.begin() as session:
        res = await upsert_new_group_pair(session, 100, 200)
        assert res == 1

    async with db.session_factory.begin() as session:
        pair: GroupPair = await session.get(GroupPair, 100)
        assert pair.public_chat_id == 200

    async with db.session_factory.begin() as session:
        await upsert_new_group_pair(session, 100, 300)
        assert res == 1

    async with db.session_factory.begin() as session:
        pair: GroupPair = await session.get(GroupPair, 100)
        assert pair.public_chat_id == 300
