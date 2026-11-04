import asyncio
import calendar
import logging
from dataclasses import dataclass

import aiohttp
import feedparser

from jeeves.textfit import fit_escaped

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 15
MESSAGE_LIMIT = 4096

FEEDS: list[str] = [
    "http://www.noob-club.ru/rss2.xml",
    "http://www.mmo-champion.com/external.php?do=rss&type=newcontent&sectionid=1&days=120&count=10",
    # проверено 2026-11-04: отвечает, но последнее видео от 2022-07
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC7Oo1q9m4vf7XrlZgOR95WA",
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCbLj9QP9FAaHs_647QckGtg",
    "https://ru.wowhead.com/news/rss/all",
    "https://raider.io/rss.xml",
]


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    published: int  # unix-секунды UTC


def parse_feed(data: bytes) -> list[NewsItem]:
    """RSS/Atom -> записи. Записи без даты или ссылки пропускаются, мусор даёт пустой список."""
    items: list[NewsItem] = []
    for entry in feedparser.parse(data).entries:
        moment = entry.get("published_parsed") or entry.get("updated_parsed")
        link = entry.get("link")
        if not moment or not link:
            continue
        items.append(NewsItem(entry.get("title", "").strip(), link, calendar.timegm(moment)))
    return items


async def _fetch_one(session: aiohttp.ClientSession, url: str) -> list[NewsItem]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)) as response:
            response.raise_for_status()
            data = await response.read()
        return parse_feed(data)
    except Exception as error:  # одна упавшая лента не должна ломать остальные
        log.warning("Лента %s недоступна: %r", url, error)
        return []


async def fetch_all(session: aiohttp.ClientSession, urls: list[str]) -> list[NewsItem]:
    results = await asyncio.gather(*(_fetch_one(session, url) for url in urls))
    return [item for items in results for item in items]


def select_new(items: list[NewsItem], since: int) -> list[NewsItem]:
    """Записи новее `since`, без дублей по ссылке, от старых к новым."""
    seen: set[str] = set()
    fresh: list[NewsItem] = []
    for item in sorted(items, key=lambda i: i.published):
        if item.published > since and item.link not in seen:
            seen.add(item.link)
            fresh.append(item)
    return fresh


def format_item(item: NewsItem) -> str:
    tail = "\n" + item.link
    return fit_escaped(item.title, MESSAGE_LIMIT - len(tail)) + tail
