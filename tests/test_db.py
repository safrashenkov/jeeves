import pytest

from jeeves.db import Database


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_all()
    yield database
    await database.close()


async def test_setting_roundtrip(db):
    assert await db.get_setting("newsUpdateTime") is None

    await db.set_setting("newsUpdateTime", "100")
    assert await db.get_setting("newsUpdateTime") == "100"

    await db.set_setting("newsUpdateTime", "200")
    assert await db.get_setting("newsUpdateTime") == "200"


async def test_chat_setting_upsert_and_filter(db):
    await db.set_chat_setting(1, "enableNews", "1")
    await db.set_chat_setting(2, "enableNews", "1")
    await db.set_chat_setting(3, "enableNews", "0")
    await db.set_chat_setting(3, "guild", "x")

    assert sorted(await db.get_chat_ids_with_setting("enableNews", "1")) == [1, 2]

    await db.set_chat_setting(1, "enableNews", "0")
    assert await db.get_chat_ids_with_setting("enableNews", "1") == [2]


async def test_migrate_chat_moves_rows_and_keeps_existing_target_value(db):
    await db.set_chat_setting(-1, "enableNews", "1")
    await db.set_chat_setting(-1, "guild", "Old")
    await db.set_chat_setting(-2, "guild", "New")

    await db.migrate_chat(-1, -2)

    assert await db.get_chat_ids_with_setting("enableNews", "1") == [-2]
    assert await db.get_chat_ids_with_setting("guild", "Old") == []
    assert await db.get_chat_ids_with_setting("guild", "New") == [-2]
