import logging

import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from database.database_connector import DatabaseConnector


logging.basicConfig(level=logging.DEBUG)


@pytest_asyncio.fixture()
async def db():
    postgres = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    postgres.start()

    test_database = DatabaseConnector(url=postgres.get_connection_url())

    await test_database.create_all()

    yield test_database

    await test_database.dispose()

    postgres.stop()
