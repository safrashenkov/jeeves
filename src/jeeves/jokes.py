import html
import logging
import random
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from jeeves.replies import Reply
from jeeves.textfit import fit_escaped

log = logging.getLogger(__name__)

# вид шутки -> (страница со случайными постами, минимальный рейтинг)
KINDS: dict[str, tuple[str, int]] = {
    "lol": ("https://wowlol.ru/random", 1000),
    "fap": ("https://wowlol.ru/wowfaprandom/", 100),
}
SPOILER_KINDS = {"fap"}  # картинки этих видов уходят под спойлер
BASE_URL = "https://wowlol.ru"
MESSAGE_LIMIT = 4096
LONG_TEXT = 500  # текст длиннее прячем под сворачиваемую цитату
QUOTE_OPEN = "<blockquote expandable>"
QUOTE_CLOSE = "</blockquote>"
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_RATING = 100_000  # выше — накрученные или служебные посты
ATTEMPTS = 3
CLICK_HINT = "Кликни, чтобы посмотреть в оригинальном размере"


@dataclass(frozen=True)
class Post:
    id: int
    rating: int
    text: str
    media: str | None


def _clean_text(text: str) -> str:
    text = text.replace(CLICK_HINT, "")
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_posts(data: bytes) -> list[Post]:
    """Посты страницы wowlol.ru: рейтинг лежит в `.rinner`, содержимое в `.binner`; связь по ссылке /q/<id>."""
    soup = BeautifulSoup(data, "html.parser")

    ratings: dict[int, int] = {}
    for span in soup.select(".rinner span[id^=result-]"):
        try:
            ratings[int(span["id"].removeprefix("result-"))] = int(span.get_text().strip())
        except ValueError:
            continue

    posts: list[Post] = []
    for body in soup.select(".binner"):
        link = body.select_one('a[href^="/q/"]')
        match = re.match(r"/q/(\d+)", link["href"]) if link else None
        if not match or int(match.group(1)) not in ratings:
            continue
        post_id = int(match.group(1))

        media = None
        image = body.select_one("img[src]")
        if image:
            media = urljoin(BASE_URL, image["src"].replace(".thumb", ""))
        frame = body.select_one("iframe[src]")
        if frame:
            media = urljoin(BASE_URL, frame["src"])

        for tag in body.select('a[href^="/q/"], img, iframe'):
            tag.decompose()
        for br in body.find_all("br"):
            br.replace_with("\n")
        posts.append(Post(post_id, ratings[post_id], _clean_text(body.get_text()), media))
    return posts


def pick_joke(posts: list[Post], min_rating: int, rng: random.Random, max_rating: int = MAX_RATING) -> Post | None:
    suitable = [p for p in posts if min_rating <= p.rating < max_rating and (p.text or p.media)]
    return rng.choice(suitable) if suitable else None


def build_reply(post: Post, spoiler: bool = False) -> Reply:
    """Пост -> ответ: картинка/гифка отдельным полем, видео ссылкой в тексте, длинный текст под цитатой."""
    media = post.media
    suffix = PurePosixPath(urlparse(media).path).suffix.lower() if media else ""
    photo = media if suffix in PHOTO_EXTENSIONS else None
    animation = media if suffix == ".gif" else None
    link = media if media and not (photo or animation) else None

    # место под ссылку резервируем и для картинок: если Telegram не сможет её загрузить, она уйдёт в тексте
    reserve = len(media) + 1 if media else 0
    quoted = len(html.escape(post.text)) > LONG_TEXT
    overhead = len(QUOTE_OPEN) + len(QUOTE_CLOSE) if quoted else 0
    escaped = fit_escaped(post.text, MESSAGE_LIMIT - overhead - reserve)

    body = f"{QUOTE_OPEN}{escaped}{QUOTE_CLOSE}" if quoted else escaped
    if link:
        body = f"{body}\n{link}" if body else link
    return Reply(text=body, photo=photo, animation=animation, spoiler=spoiler)


async def fetch_joke(
    session: aiohttp.ClientSession,
    kind: str,
    rng: random.Random | None = None,
    attempts: int = ATTEMPTS,
) -> Reply | None:
    """Случайный пост нужного вида; None, если сайт недоступен или подходящего поста не нашлось."""
    url, min_rating = KINDS[kind]
    rng = rng or random.Random()
    for _ in range(attempts):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                response.raise_for_status()
                data = await response.read()
        except Exception as error:
            log.warning("wowlol недоступен: %r", error)
            continue
        post = pick_joke(parse_posts(data), min_rating, rng)
        if post:
            return build_reply(post, spoiler=kind in SPOILER_KINDS)
    return None
