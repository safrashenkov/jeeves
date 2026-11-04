from collections.abc import Awaitable, Callable

from jeeves.db import Database

Handler = Callable[[int, Database], Awaitable[str]]

HELP_TEXT = (
    "Вас приветствует Дживс. Я помощник для чатов гильдий World of Warcraft.\n"
    "Обращайтесь ко мне по имени, например: «Дживс, включи новости».\n\n"
    "Что я умею сейчас:\n"
    "— Дживс, включи новости — присылать в чат новости про WoW\n"
    "— Дживс, выключи новости — перестать присылать\n"
    "— Дживс, помощь — этот список\n\n"
    "Остальное я постепенно вспоминаю."
)


async def news_on(chat_id: int, db: Database) -> str:
    await db.set_chat_setting(chat_id, "enableNews", "1")
    return "Подписка на новости включена"


async def news_off(chat_id: int, db: Database) -> str:
    await db.set_chat_setting(chat_id, "enableNews", "0")
    return "Подписка на новости отключена"


async def help_(chat_id: int, db: Database) -> str:
    return HELP_TEXT


async def unknown(chat_id: int, db: Database) -> str:
    return "Простите, не понял. Список команд: /help"


HANDLERS: dict[str, Handler] = {
    "news_on": news_on,
    "news_off": news_off,
    "help": help_,
    "unknown": unknown,
}
