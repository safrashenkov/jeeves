import random

from fakes import FakeSession

from jeeves.jokes import KINDS, LONG_TEXT, MESSAGE_LIMIT, Post, build_reply, fetch_joke, parse_posts, pick_joke
from jeeves.replies import Reply

PAGE = """<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head><body>
<div class="post"><div><div><div class="rinner"><span id="result-1">1500</span></div></div></div>
  <div class="binner"> Шутка раз<br/><br/><br/><a href="/q/1#disqus_thread">Оставить комментарий</a> </div></div>
<div class="post"><div><div><div class="rinner"><span id="result-2">40</span></div></div></div>
  <div class="binner"><i>Подпись к картинке</i> <br/>
    <a class="highslide" href="http://wowlol.ru/img3/abc.jpg"><img src="http://wowlol.ru/img3/abc.thumb.jpg"/></a>
    <i>Кликни, чтобы посмотреть в оригинальном размере</i><br/>
    <a href="/q/2#disqus_thread">Оставить комментарий</a> </div></div>
<div class="post"><div><div><div class="rinner"><span id="result-3">999999</span></div></div></div>
  <div class="binner">Видео<br/><iframe src="https://www.youtube.com/embed/xyz"></iframe>
    <a href="/q/3#disqus_thread">Оставить комментарий</a></div></div>
<div class="post"><div><div><div class="rinner"><span id="result-4">n/a</span></div></div></div>
  <div class="binner">Без рейтинга<a href="/q/4#disqus_thread">x</a></div></div>
</body></html>""".encode("utf-8")


def test_parse_posts_extracts_rating_text_and_media():
    posts = {p.id: p for p in parse_posts(PAGE)}

    assert posts[1] == Post(1, 1500, "Шутка раз", None)
    assert posts[2] == Post(2, 40, "Подпись к картинке", "http://wowlol.ru/img3/abc.jpg")
    assert posts[3] == Post(3, 999999, "Видео", "https://www.youtube.com/embed/xyz")
    assert 4 not in posts  # рейтинг не число


def test_relative_media_urls_become_absolute():
    page = (
        '<div class="rinner"><span id="result-7">500</span></div>'
        '<div class="binner"><img src="/img0/8397bc71.thumb.jpg"/><a href="/q/7#d">x</a></div>'
    ).encode()

    assert parse_posts(page) == [Post(7, 500, "", "https://wowlol.ru/img0/8397bc71.jpg")]


def test_parse_garbage_returns_empty():
    assert parse_posts(b"<html>nothing here") == []
    assert parse_posts(b"") == []


def test_pick_joke_respects_rating_window():
    posts = parse_posts(PAGE)
    rng = random.Random(0)

    assert pick_joke(posts, min_rating=1000, rng=rng).id == 1  # 3-й выше потолка, 2-й ниже порога
    assert pick_joke(posts, min_rating=5000, rng=rng) is None
    assert pick_joke([], min_rating=0, rng=rng) is None


def test_reply_text_only_is_escaped():
    assert build_reply(Post(1, 1, "a < b & c", None)) == Reply(text="a &lt; b &amp; c")


def test_reply_picture_goes_to_photo_field():
    assert build_reply(Post(1, 1, "Подпись", "http://x/y.JPG")) == Reply(text="Подпись", photo="http://x/y.JPG")
    assert build_reply(Post(1, 1, "", "http://x/y.png")) == Reply(text="", photo="http://x/y.png")


def test_reply_gif_goes_to_animation_field():
    assert build_reply(Post(1, 1, "Гифка", "http://x/y.gif")) == Reply(text="Гифка", animation="http://x/y.gif")


def test_reply_video_stays_a_link_in_text():
    reply = build_reply(Post(1, 1, "Видео", "https://www.youtube.com/embed/xyz"))

    assert reply == Reply(text="Видео\nhttps://www.youtube.com/embed/xyz")


def test_reply_spoiler_flag_is_passed_through():
    assert build_reply(Post(1, 1, "", "http://x/y.jpg"), spoiler=True).spoiler is True


def test_long_text_is_hidden_under_expandable_blockquote():
    short = build_reply(Post(1, 1, "я" * LONG_TEXT, None))
    long = build_reply(Post(1, 1, "я" * (LONG_TEXT + 1), None))

    assert short.text == "я" * LONG_TEXT
    assert long.text == "<blockquote expandable>" + "я" * (LONG_TEXT + 1) + "</blockquote>"


def test_huge_text_is_truncated_to_telegram_limit_keeping_markup_valid():
    url = "https://www.youtube.com/embed/xyz"
    reply = build_reply(Post(1, 1, "я&" * 5000, url))

    assert len(reply.text) <= MESSAGE_LIMIT
    assert reply.text.startswith("<blockquote expandable>")
    assert reply.text.endswith("</blockquote>\n" + url)
    assert "&amp;" in reply.text and "&am</" not in reply.text  # сущность не разрезана


async def test_fetch_joke_retries_until_a_good_post_is_found():
    url, min_rating = KINDS["lol"]
    weak = PAGE.replace(b"1500", b"10")
    session = FakeSession({url: [weak, PAGE]})

    reply = await fetch_joke(session, "lol", rng=random.Random(0))

    assert reply == Reply(text="Шутка раз")
    assert len(session.calls) == 2
    assert min_rating == 1000


async def test_fap_pictures_are_spoilered_but_lol_ones_are_not():
    fap_url, _ = KINDS["fap"]
    lol_url, _ = KINDS["lol"]
    page = PAGE.replace(b'<span id="result-2">40</span>', b'<span id="result-2">5000</span>').replace(b"1500", b"10")

    fap = await fetch_joke(FakeSession({fap_url: page}), "fap", rng=random.Random(0))
    lol = await fetch_joke(FakeSession({lol_url: page}), "lol", rng=random.Random(0))

    assert fap == Reply(text="Подпись к картинке", photo="http://wowlol.ru/img3/abc.jpg", spoiler=True)
    assert lol == Reply(text="Подпись к картинке", photo="http://wowlol.ru/img3/abc.jpg", spoiler=False)


async def test_fetch_joke_returns_none_when_site_is_down_or_empty():
    url, _ = KINDS["lol"]

    assert await fetch_joke(FakeSession({url: TimeoutError("down")}), "lol") is None
    assert await fetch_joke(FakeSession({url: b"<html>"}), "lol") is None
