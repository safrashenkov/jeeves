import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from jeeves.config import Settings
from jeeves.handlers import HANDLERS, Context
from jeeves.replies import Reply
from jeeves.router import parse_command

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024


def bot_commands() -> list[BotCommand]:
    """Меню «/» в Telegram. Каждая команда должна понимать router.SLASH."""
    return [
        BotCommand(command="news_on", description="Включить новости в этом чате"),
        BotCommand(command="news_off", description="Выключить новости"),
        BotCommand(command="token", description="Цена жетона WoW"),
        BotCommand(command="joke", description="Случайная шутка с wowlol.ru"),
        BotCommand(command="fap", description="Случайный пост WoWFap с wowlol.ru"),
        BotCommand(command="help", description="Что я умею"),
    ]


async def send_reply(message: Message, reply: str | Reply) -> None:
    if isinstance(reply, str):
        await message.reply(reply)
        return

    media = reply.photo or reply.animation
    if not media:
        await message.reply(reply.text)
        return

    caption = reply.text if reply.text and len(reply.text) <= CAPTION_LIMIT else None
    try:
        if reply.photo:
            await message.reply_photo(reply.photo, caption=caption, has_spoiler=reply.spoiler)
        else:
            await message.reply_animation(reply.animation, caption=caption, has_spoiler=reply.spoiler)
    except TelegramBadRequest as error:
        # Telegram сам скачивает картинку по ссылке; если не вышло, отдаём ссылку текстом
        log.warning("Не удалось отправить медиа %s: %s", media, error)
        await message.reply(f"{reply.text}\n{media}" if reply.text else media)
        return
    if reply.text and caption is None:
        await message.reply(reply.text)


def build_dispatcher(ctx: Context, bot_name: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message()
    async def on_message(message: Message) -> None:
        key = parse_command(message.text, message.chat.id, bot_name)
        if key is None:
            return
        await send_reply(message, await HANDLERS[key](message.chat.id, ctx))

    return dp


def create_app(settings: Settings, ctx: Context, bot: Bot) -> web.Application:
    app = web.Application()

    async def healthz(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/healthz", healthz)
    SimpleRequestHandler(
        dispatcher=build_dispatcher(ctx, settings.bot_name),
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)
    return app
