import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from jeeves.db import Database
from jeeves.money import format_gold
from jeeves.replies import Reply

log = logging.getLogger(__name__)


@dataclass
class Context:
    """Всё, что нужно обработчикам команд. Источники данных необязательны: без них команда отвечает заглушкой."""

    db: Database
    token_price: Callable[[], Awaitable[int]] | None = None
    joke: Callable[[str], Awaitable[Reply | None]] | None = None


Handler = Callable[[int, Context], Awaitable[str | Reply]]

HELP_TEXT = (
    "Вас приветствует Дживс. Я помощник для чатов гильдий World of Warcraft.\n"
    "Обращайтесь ко мне по имени, например: «Дживс, включи новости».\n\n"
    "Что я умею сейчас:\n"
    "— Дживс, включи новости — присылать в чат новости про WoW\n"
    "— Дживс, выключи новости — перестать присылать\n"
    "— Дживс, жетон — цена жетона WoW в европейском регионе\n"
    "— Дживс, шут — случайная шутка с wowlol.ru\n"
    "— Дживс, фап — случайный пост из раздела WoWFap на wowlol.ru\n"
    "— Дживс, помощь — этот список\n\n"
    "Остальное я постепенно вспоминаю."
)


async def news_on(chat_id: int, ctx: Context) -> str:
    await ctx.db.set_chat_setting(chat_id, "enableNews", "1")
    return "Подписка на новости включена"


async def news_off(chat_id: int, ctx: Context) -> str:
    await ctx.db.set_chat_setting(chat_id, "enableNews", "0")
    return "Подписка на новости отключена"


async def help_(chat_id: int, ctx: Context) -> str:
    return HELP_TEXT


async def unknown(chat_id: int, ctx: Context) -> str:
    return "Простите, не понял. Список команд: /help"


async def token(chat_id: int, ctx: Context) -> str:
    if ctx.token_price is None:
        return "Цена жетона пока недоступна: не настроен доступ к Blizzard API"
    try:
        price = await ctx.token_price()
    except Exception:
        log.exception("Не удалось получить цену жетона")
        return "Не получилось узнать цену жетона, попробуйте позже"
    return f"Сейчас жетон WoW в европейском регионе стоит {format_gold(price)}"


def _joke_handler(kind: str) -> Handler:
    async def handler(chat_id: int, ctx: Context) -> str | Reply:
        if ctx.joke is not None:
            try:
                reply = await ctx.joke(kind)
            except Exception:
                log.exception("Не удалось получить шутку (%s)", kind)
                reply = None
            if reply:
                return reply
        return "Мне не до смеха!"

    return handler


HANDLERS: dict[str, Handler] = {
    "news_on": news_on,
    "news_off": news_off,
    "help": help_,
    "unknown": unknown,
    "token": token,
    "wowlol": _joke_handler("lol"),
    "wowfap": _joke_handler("fap"),
}
