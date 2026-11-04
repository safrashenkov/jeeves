import pytest

from jeeves.db import Database
from jeeves.handlers import HANDLERS


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_all()
    yield database
    await database.close()


async def test_news_on_subscribes_chat(db):
    reply = await HANDLERS["news_on"](-5, db)

    assert reply == "Подписка на новости включена"
    assert await db.get_chat_ids_with_setting("enableNews", "1") == [-5]


async def test_news_off_unsubscribes_chat(db):
    await HANDLERS["news_on"](-5, db)

    reply = await HANDLERS["news_off"](-5, db)

    assert reply == "Подписка на новости отключена"
    assert await db.get_chat_ids_with_setting("enableNews", "1") == []
    assert await db.get_chat_ids_with_setting("enableNews", "0") == [-5]


async def test_help_lists_news_commands(db):
    reply = await HANDLERS["help"](1, db)

    assert "включи новости" in reply
    assert "выключи новости" in reply


async def test_unknown_points_to_help(db):
    assert await HANDLERS["unknown"](1, db) == "Простите, не понял. Список команд: /help"
