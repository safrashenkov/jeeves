from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from jeeves.config import Settings
from jeeves.db import Database
from jeeves.handlers import HANDLERS
from jeeves.router import parse_command


def build_dispatcher(db: Database, bot_name: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message()
    async def on_message(message: Message) -> None:
        key = parse_command(message.text, message.chat.id, bot_name)
        if key is None:
            return
        reply = await HANDLERS[key](message.chat.id, db)
        await message.reply(reply)

    return dp


def create_app(settings: Settings, db: Database, bot: Bot) -> web.Application:
    app = web.Application()

    async def healthz(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/healthz", healthz)
    SimpleRequestHandler(
        dispatcher=build_dispatcher(db, settings.bot_name),
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)
    return app
