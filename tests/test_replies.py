"""Как ответы-картинки уходят в Telegram: фото, гифка, длинный текст, откат на ссылку, меню команд."""
import re

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from jeeves.app import bot_commands, build_dispatcher
from jeeves.db import Database
from jeeves.handlers import HANDLERS, Context
from jeeves.replies import Reply
from jeeves.router import parse_command


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
def calls(monkeypatch):
    recorded = []

    async def fake_call(self, method, request_timeout=None):
        recorded.append(method)

    monkeypatch.setattr(Bot, "__call__", fake_call)
    return recorded


def update(text: str) -> dict:
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


def dispatcher_with(db, reply):
    async def joke(kind: str):
        return reply

    return build_dispatcher(Context(db=db, joke=joke), "jeeves_bot")


async def test_text_reply_is_sent_as_message(db, bot, calls):
    await dispatcher_with(db, Reply(text="смешно")).feed_raw_update(bot, update("Дживс, шут"))

    assert [type(c).__name__ for c in calls] == ["SendMessage"]
    assert calls[0].text == "смешно"


async def test_picture_with_short_text_is_sent_as_photo_with_caption_and_spoiler(db, bot, calls):
    reply = Reply(text="Подпись", photo="http://x/y.jpg", spoiler=True)

    await dispatcher_with(db, reply).feed_raw_update(bot, update("Дживс, фап"))

    assert [type(c).__name__ for c in calls] == ["SendPhoto"]
    assert (calls[0].photo, calls[0].caption, calls[0].has_spoiler) == ("http://x/y.jpg", "Подпись", True)


async def test_picture_with_long_text_sends_photo_then_text(db, bot, calls):
    text = "<blockquote expandable>" + "я" * 1500 + "</blockquote>"

    await dispatcher_with(db, Reply(text=text, photo="http://x/y.jpg")).feed_raw_update(bot, update("Дживс, шут"))

    assert [type(c).__name__ for c in calls] == ["SendPhoto", "SendMessage"]
    assert calls[0].caption is None
    assert calls[1].text == text


async def test_gif_is_sent_as_animation(db, bot, calls):
    reply = Reply(text="Гифка", animation="http://x/y.gif")

    await dispatcher_with(db, reply).feed_raw_update(bot, update("Дживс, шут"))

    assert [type(c).__name__ for c in calls] == ["SendAnimation"]


async def test_picture_telegram_cannot_fetch_falls_back_to_link(db, bot, monkeypatch):
    sent = []

    async def fake_call(self, method, request_timeout=None):
        if type(method).__name__ == "SendPhoto":
            raise TelegramBadRequest(method, "Bad Request: failed to get HTTP URL content")
        sent.append(method)

    monkeypatch.setattr(Bot, "__call__", fake_call)

    await dispatcher_with(db, Reply(text="Подпись", photo="http://x/y.jpg")).feed_raw_update(bot, update("Дживс, шут"))

    assert [(type(m).__name__, m.text) for m in sent] == [("SendMessage", "Подпись\nhttp://x/y.jpg")]


def test_command_menu_matches_what_the_bot_understands():
    commands = bot_commands()

    assert {c.command for c in commands} >= {"help", "news_on", "news_off", "token", "joke", "fap"}
    for command in commands:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", command.command)
        assert 0 < len(command.description) <= 256
        key = parse_command("/" + command.command, -100, "jeeves_bot")
        assert key in HANDLERS and key != "unknown", command.command
