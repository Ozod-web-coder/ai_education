import asyncio

import pytest
from asgiref.sync import sync_to_async
from django.db import connections


@pytest.fixture(autouse=True)
def close_bot_db_connections():
    """Асинхронные обработчики ходят в базу из отдельного потока asgiref.
    Закрываем его соединение, иначе pytest не сможет удалить тестовую базу."""
    yield
    asyncio.run(sync_to_async(connections.close_all)())
