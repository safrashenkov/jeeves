import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramRetryAfter,
)

from jeeves.db import Database
from jeeves.news import NewsItem, format_item, select_new

log = logging.getLogger(__name__)

STALE_AFTER = 24 * 3600
SETTING = "newsUpdateTime"

Send = Callable[[int, str], Awaitable[None]]


async def _deliver(db: Database, send: Send, chat_id: int, text: str) -> int | None:
    """Отправляет текст в чат. Возвращает актуальный ID чата или None, если чат отписан."""
    try:
        try:
            await send(chat_id, text)
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after)
            await send(chat_id, text)
        return chat_id
    except TelegramMigrateToChat as error:
        new_id = error.migrate_to_chat_id
        await db.migrate_chat(chat_id, new_id)
        try:
            await send(new_id, text)
        except Exception:
            log.exception("Не удалось отправить в перенесённый чат %s", new_id)
        return new_id
    except TelegramForbiddenError:
        log.info("Чат %s заблокировал бота, отключаю новости", chat_id)
    except TelegramBadRequest as error:
        if "chat not found" not in error.message.lower():
            log.exception("Ошибка отправки в чат %s", chat_id)
            return chat_id
        log.info("Чат %s не найден, отключаю новости", chat_id)
    except Exception:
        log.exception("Ошибка отправки в чат %s", chat_id)
        return chat_id
    await db.set_chat_setting(chat_id, "enableNews", "0")
    return None


async def run_news_cycle(
    db: Database,
    fetch: Callable[[], Awaitable[list[NewsItem]]],
    send: Send,
    now: int,
    pause: float = 0.05,
) -> int:
    """Один проход: получить ленты, разослать новое. Возвращает число разосланных записей."""
    raw = await db.get_setting(SETTING)
    since = int(raw) if raw and raw.isdigit() else None
    if since is None or since < now - STALE_AFTER:
        await db.set_setting(SETTING, str(now))
        return 0

    # запись с датой в будущем подождёт своего времени: иначе она бы сдвинула метку вперёд
    items = [item for item in await fetch() if item.published <= now]
    fresh = select_new(items, since)
    chats = await db.get_chat_ids_with_setting("enableNews", "1")

    for item in fresh:
        text = format_item(item)
        active: list[int] = []
        for chat_id in chats:
            new_id = await _deliver(db, send, chat_id, text)
            if new_id is not None:
                active.append(new_id)
            await asyncio.sleep(pause)
        chats = active

    if fresh:
        await db.set_setting(SETTING, str(max(item.published for item in fresh)))
    return len(fresh)


async def news_loop(
    run_once: Callable[[], Awaitable[object]],
    interval: float,
    on_error: Callable[[str], Awaitable[None]],
) -> None:
    while True:
        try:
            await run_once()
        except Exception as error:
            log.exception("Сбой цикла новостей")
            try:
                await on_error(f"Сбой цикла новостей: {error!r}")
            except Exception:
                log.exception("Не удалось оповестить админа")
        await asyncio.sleep(interval)
