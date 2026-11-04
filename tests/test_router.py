import pytest

from jeeves.router import parse_command

BOT = "jeeves_bot"
GROUP = -100123
PRIVATE = 42


@pytest.mark.parametrize(
    ("text", "chat_id", "expected"),
    [
        ("включи новости", PRIVATE, "news_on"),
        ("Дживс, включи новости!", GROUP, "news_on"),
        ("Дживс, отключи новости", GROUP, "news_off"),
        ("дживс выключи новости", GROUP, "news_off"),
        ("включи новости", GROUP, None),
        ("/news_on@jeeves_bot", GROUP, "news_on"),
        ("/news_on@other_bot", GROUP, None),
        ("/news_off", GROUP, "news_off"),
        ("/start", PRIVATE, "help"),
        ("/help@jeeves_bot", GROUP, "help"),
        ("Дживс, помощь", GROUP, "help"),
        ("Дживс, расскажи анекдот", GROUP, "unknown"),
        ("привет", PRIVATE, "unknown"),
        ("просто болтаем", GROUP, None),
    ],
)
def test_parse_command(text, chat_id, expected):
    assert parse_command(text, chat_id, BOT) == expected


@pytest.mark.parametrize("chat_id", [GROUP, PRIVATE])
@pytest.mark.parametrize("text", [None, "", "   "])
def test_non_text_message_is_ignored(text, chat_id):
    assert parse_command(text, chat_id, BOT) is None
