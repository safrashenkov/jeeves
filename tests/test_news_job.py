import asyncio

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage

from jeeves.db import Database
from jeeves.news import NewsItem
from jeeves.news_job import news_loop, run_news_cycle

NOW = 1_700_000_000
METHOD = SendMessage(chat_id=1, text="x")


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_all()
    yield database
    await database.close()


def feed(*items: NewsItem):
    async def fetch():
        return list(items)

    return fetch


class Sender:
    """Записывает отправки; для выбранных чатов бросает заданные исключения."""

    def __init__(self, failures: dict[int, list[Exception]] | None = None):
        self.sent: list[tuple[int, str]] = []
        self.failures = failures or {}

    async def __call__(self, chat_id: int, text: str) -> None:
        queue = self.failures.get(chat_id)
        if queue:
            raise queue.pop(0)
        self.sent.append((chat_id, text))


async def subscribe(db, *chat_ids):
    for chat_id in chat_ids:
        await db.set_chat_setting(chat_id, "enableNews", "1")


async def test_first_run_resets_missing_timestamp_and_sends_nothing(db):
    await subscribe(db, 1)
    sender = Sender()

    count = await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 10)), sender, NOW, pause=0)

    assert count == 0
    assert sender.sent == []
    assert await db.get_setting("newsUpdateTime") == str(NOW)


async def test_stale_timestamp_over_24h_resets(db):
    await subscribe(db, 1)
    await db.set_setting("newsUpdateTime", str(NOW - 86400 - 1))
    sender = Sender()

    count = await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 10)), sender, NOW, pause=0)

    assert count == 0
    assert sender.sent == []
    assert await db.get_setting("newsUpdateTime") == str(NOW)


async def test_sends_new_items_oldest_first_to_subscribed_chats_only(db):
    await subscribe(db, 1, 2)
    await db.set_chat_setting(3, "enableNews", "0")
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender()
    items = [
        NewsItem("newer", "http://x/n", NOW - 100),
        NewsItem("old", "http://x/o", NOW - 2000),
        NewsItem("older-new", "http://x/a", NOW - 500),
    ]

    count = await run_news_cycle(db, feed(*items), sender, NOW, pause=0)

    assert count == 2
    assert [text.split("\n")[0] for chat, text in sender.sent if chat == 1] == ["older-new", "newer"]
    assert {chat for chat, _ in sender.sent} == {1, 2}
    assert await db.get_setting("newsUpdateTime") == str(NOW - 100)


async def test_future_pubdate_is_not_sent_and_does_not_advance_timestamp(db):
    await subscribe(db, 1)
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender()
    items = [NewsItem("future", "http://x/f", NOW + 10**7), NewsItem("ok", "http://x/ok", NOW - 5)]

    await run_news_cycle(db, feed(*items), sender, NOW, pause=0)

    assert [text.split("\n")[0] for _, text in sender.sent] == ["ok"]
    assert int(await db.get_setting("newsUpdateTime")) <= NOW


async def test_no_subscribed_chats_still_advances_timestamp(db):
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender()

    await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 50)), sender, NOW, pause=0)

    assert sender.sent == []
    assert await db.get_setting("newsUpdateTime") == str(NOW - 50)


async def test_blocked_chat_is_disabled_and_others_still_receive(db):
    await subscribe(db, 1, 2)
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender({1: [TelegramForbiddenError(METHOD, "Forbidden: bot was blocked by the user")]})

    await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 50)), sender, NOW, pause=0)

    assert [chat for chat, _ in sender.sent] == [2]
    assert await db.get_chat_ids_with_setting("enableNews", "1") == [2]
    assert await db.get_chat_ids_with_setting("enableNews", "0") == [1]


async def test_chat_not_found_disables_chat(db):
    await subscribe(db, 1)
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender({1: [TelegramBadRequest(METHOD, "Bad Request: chat not found")]})

    await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 50)), sender, NOW, pause=0)

    assert await db.get_chat_ids_with_setting("enableNews", "0") == [1]


async def test_migrate_to_chat_retargets_and_retries(db):
    await subscribe(db, -1)
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender({-1: [TelegramMigrateToChat(METHOD, "Bad Request: group chat was upgraded", -100)]})

    await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 50)), sender, NOW, pause=0)

    assert [chat for chat, _ in sender.sent] == [-100]
    assert await db.get_chat_ids_with_setting("enableNews", "1") == [-100]


async def test_retry_after_is_retried_once(db):
    await subscribe(db, 1)
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender({1: [TelegramRetryAfter(METHOD, "Too Many Requests", 0)]})

    await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 50)), sender, NOW, pause=0)

    assert [chat for chat, _ in sender.sent] == [1]


async def test_unexpected_error_in_one_chat_does_not_stop_the_rest(db):
    await subscribe(db, 1, 2)
    await db.set_setting("newsUpdateTime", str(NOW - 1000))
    sender = Sender({1: [RuntimeError("boom")]})

    await run_news_cycle(db, feed(NewsItem("t", "http://x/1", NOW - 50)), sender, NOW, pause=0)

    assert [chat for chat, _ in sender.sent] == [2]
    assert await db.get_chat_ids_with_setting("enableNews", "1") == [1, 2]


async def test_news_loop_survives_exception_and_reports():
    calls = 0
    errors: list[str] = []

    async def run_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")

    async def on_error(text: str) -> None:
        errors.append(text)

    task = asyncio.create_task(news_loop(run_once, 0, on_error))
    for _ in range(100):
        if calls >= 3:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls >= 3
    assert len(errors) == 1 and "boom" in errors[0]
