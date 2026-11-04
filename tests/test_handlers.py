import pytest

from jeeves.db import Database
from jeeves.handlers import HANDLERS, Context
from jeeves.replies import Reply


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_all()
    yield database
    await database.close()


@pytest.fixture
def ctx(db):
    return Context(db=db)


async def test_news_on_subscribes_chat(ctx, db):
    reply = await HANDLERS["news_on"](-5, ctx)

    assert reply == "Подписка на новости включена"
    assert await db.get_chat_ids_with_setting("enableNews", "1") == [-5]


async def test_news_off_unsubscribes_chat(ctx, db):
    await HANDLERS["news_on"](-5, ctx)

    reply = await HANDLERS["news_off"](-5, ctx)

    assert reply == "Подписка на новости отключена"
    assert await db.get_chat_ids_with_setting("enableNews", "1") == []
    assert await db.get_chat_ids_with_setting("enableNews", "0") == [-5]


async def test_help_lists_commands(ctx):
    reply = await HANDLERS["help"](1, ctx)

    for phrase in ("включи новости", "выключи новости", "жетон", "шут", "фап"):
        assert phrase in reply


async def test_unknown_points_to_help(ctx):
    assert await HANDLERS["unknown"](1, ctx) == "Простите, не понял. Список команд: /help"


async def test_token_replies_with_gold_price(db):
    async def price() -> int:
        return 2_450_000_000

    reply = await HANDLERS["token"](1, Context(db=db, token_price=price))

    assert reply == "Сейчас жетон WoW в европейском регионе стоит 245 000 г"


async def test_token_without_blizzard_access(ctx):
    reply = await HANDLERS["token"](1, ctx)

    assert "недоступна" in reply


async def test_token_apologizes_when_api_fails(db):
    async def price() -> int:
        raise RuntimeError("boom")

    reply = await HANDLERS["token"](1, Context(db=db, token_price=price))

    assert "Не получилось" in reply


@pytest.mark.parametrize(("key", "kind"), [("wowlol", "lol"), ("wowfap", "fap")])
async def test_joke_handlers_use_matching_kind(db, key, kind):
    asked = []

    async def joke(k: str) -> Reply | None:
        asked.append(k)
        return Reply(text="смешно")

    reply = await HANDLERS[key](1, Context(db=db, joke=joke))

    assert reply == Reply(text="смешно")
    assert asked == [kind]


async def test_joke_falls_back_when_nothing_found(db):
    async def joke(kind: str) -> Reply | None:
        return None

    async def broken(kind: str) -> Reply | None:
        raise RuntimeError("boom")

    assert await HANDLERS["wowlol"](1, Context(db=db, joke=joke)) == "Мне не до смеха!"
    assert await HANDLERS["wowlol"](1, Context(db=db, joke=broken)) == "Мне не до смеха!"
    assert await HANDLERS["wowlol"](1, Context(db=db)) == "Мне не до смеха!"
