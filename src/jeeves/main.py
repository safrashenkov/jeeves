import asyncio
import logging
import time

import aiohttp
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from jeeves.alerts import AdminNotifier
from jeeves.app import create_app
from jeeves.config import get_settings
from jeeves.db import Database
from jeeves.news import FEEDS, fetch_all
from jeeves.news_job import news_loop, run_news_cycle

log = logging.getLogger("jeeves")


async def serve() -> None:
    settings = get_settings()
    db = Database(settings.db_url)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    http = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (compatible; JeevesBot)"})

    async def send_news(chat_id: int, text: str) -> None:
        await bot.send_message(chat_id, text)

    async def send_admin(text: str) -> None:
        await bot.send_message(settings.admin_id, text, parse_mode=None)

    notifier = AdminNotifier(send_admin)

    async def run_once() -> int:
        return await run_news_cycle(db, lambda: fetch_all(http, FEEDS), send_news, int(time.time()))

    app = create_app(settings, db, bot)
    runner = web.AppRunner(app)
    news_task: asyncio.Task | None = None
    try:
        await runner.setup()
        await web.TCPSite(runner, settings.listen_host, settings.listen_port).start()
        log.info("Слушаю %s:%s", settings.listen_host, settings.listen_port)
        # вебхук ставим после старта сервера, чтобы первые апдейты не ушли в пустоту
        await bot.set_webhook(
            settings.webhook_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=False,
        )
        log.info("Вебхук установлен: %s", settings.webhook_url)
        news_task = asyncio.create_task(news_loop(run_once, settings.news_interval_seconds, notifier.notify))
        await asyncio.Event().wait()
    finally:
        if news_task:
            news_task.cancel()
        await runner.cleanup()
        await http.close()
        await bot.session.close()
        await db.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
