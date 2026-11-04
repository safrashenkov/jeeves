import calendar

from jeeves.news import NewsItem, fetch_all, format_item, parse_feed, select_new

T1 = calendar.timegm((2023, 1, 2, 10, 0, 0))
T2 = calendar.timegm((2023, 1, 3, 12, 30, 0))

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
  <item><title>First</title><link>http://x/1</link>
        <pubDate>Mon, 02 Jan 2023 10:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
  <entry><title>Second</title><link href="http://x/2"/>
         <published>2023-01-03T12:30:00+00:00</published></entry>
</feed>"""

NO_DATE = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
  <item><title>Dateless</title><link>http://x/3</link></item>
  <item><title>Dated</title><link>http://x/1</link>
        <pubDate>Mon, 02 Jan 2023 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_rss_and_atom():
    assert parse_feed(RSS) == [NewsItem("First", "http://x/1", T1)]
    assert parse_feed(ATOM) == [NewsItem("Second", "http://x/2", T2)]


def test_parse_skips_items_without_date():
    assert parse_feed(NO_DATE) == [NewsItem("Dated", "http://x/1", T1)]


def test_parse_garbage_returns_empty():
    assert parse_feed(b"<html>not a feed at all") == []
    assert parse_feed(b"") == []


def test_select_new_filters_dedups_and_sorts():
    items = [
        NewsItem("B", "http://x/b", 30),
        NewsItem("old", "http://x/old", 10),
        NewsItem("A", "http://x/a", 20),
        NewsItem("B again", "http://x/b", 30),
    ]

    result = select_new(items, since=10)

    assert [i.link for i in result] == ["http://x/a", "http://x/b"]


def test_format_item_escapes_and_truncates():
    assert format_item(NewsItem("A & <b>", "http://x", 1)) == "A &amp; &lt;b&gt;\nhttp://x"

    long_text = format_item(NewsItem("я" * 5000, "http://x/very/long", 1))
    assert len(long_text) <= 4096
    assert long_text.endswith("\nhttp://x/very/long")


class FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def raise_for_status(self):
        pass

    async def read(self):
        return self._data


class FakeRequest:
    def __init__(self, outcome):
        self._outcome = outcome

    async def __aenter__(self):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return FakeResponse(self._outcome)

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, outcomes: dict):
        self._outcomes = outcomes

    def get(self, url, **kwargs):
        return FakeRequest(self._outcomes[url])


async def test_fetch_all_survives_failing_feed():
    session = FakeSession({"http://bad": TimeoutError("boom"), "http://ok": RSS, "http://junk": b"<html>"})

    items = await fetch_all(session, ["http://bad", "http://ok", "http://junk"])

    assert items == [NewsItem("First", "http://x/1", T1)]
