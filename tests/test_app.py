import pytest
from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

from jeeves.app import build_dispatcher, create_app
from jeeves.config import Settings
from jeeves.db import Database
from jeeves.handlers import Context


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_all()
    yield database
    await database.close()


@pytest.fixture
async def bot():
    instance = Bot("123:abc")
    yield instance
    await instance.session.close()


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        bot_token="123:abc",
        bot_name="jeeves_bot",
        admin_id=1,
        webhook_base_url="https://jeeves.perm-bear.ru",
        webhook_secret="s3cret",
        db_user="u",
        db_password="p",
    )


@pytest.fixture
def calls(monkeypatch):
    """Перехватывает исходящие вызовы Telegram API вместо сети."""
    recorded = []

    async def fake_call(self, method, request_timeout=None):
        recorded.append(method)

    monkeypatch.setattr(Bot, "__call__", fake_call)
    return recorded


def group_update(text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": 1_700_000_000,
            "chat": {"id": -100123, "type": "supergroup", "title": "Guild"},
            "from": {"id": 7, "is_bot": False, "first_name": "Orc"},
            "text": text,
        },
    }


async def test_healthz_ok(settings, db, bot):
    async with TestClient(TestServer(create_app(settings, Context(db=db), bot))) as client:
        response = await client.get("/healthz")

        assert response.status == 200
        assert await response.text() == "ok"


async def test_webhook_rejects_missing_secret(settings, db, bot):
    async with TestClient(TestServer(create_app(settings, Context(db=db), bot))) as client:
        response = await client.post(settings.webhook_path, json=group_update("Дживс, помощь"))

        assert response.status == 401


async def test_webhook_rejects_wrong_secret_and_accepts_right_one(settings, db, bot, calls):
    header = "X-Telegram-Bot-Api-Secret-Token"
    update = group_update("всем привет")
    async with TestClient(TestServer(create_app(settings, Context(db=db), bot))) as client:
        wrong = await client.post(settings.webhook_path, json=update, headers={header: "nope"})
        right = await client.post(settings.webhook_path, json=update, headers={header: "s3cret"})

        assert wrong.status == 401
        assert right.status == 200


async def test_dispatcher_replies_to_news_on(db, bot, calls):
    dp = build_dispatcher(Context(db=db), "jeeves_bot")

    await dp.feed_raw_update(bot, group_update("Дживс, включи новости"))

    assert await db.get_chat_ids_with_setting("enableNews", "1") == [-100123]
    assert [c.text for c in calls] == ["Подписка на новости включена"]


async def test_dispatcher_ignores_unaddressed_group_message(db, bot, calls):
    dp = build_dispatcher(Context(db=db), "jeeves_bot")

    await dp.feed_raw_update(bot, group_update("всем привет, кто на рейд?"))

    assert calls == []
    assert await db.get_chat_ids_with_setting("enableNews", "1") == []


async def test_dispatcher_survives_message_without_text(db, bot, calls):
    dp = build_dispatcher(Context(db=db), "jeeves_bot")
    update = group_update("x")
    del update["message"]["text"]
    update["message"]["sticker"] = {
        "file_id": "f", "file_unique_id": "u", "type": "regular",
        "width": 1, "height": 1, "is_animated": False, "is_video": False,
    }

    await dp.feed_raw_update(bot, update)

    assert calls == []
