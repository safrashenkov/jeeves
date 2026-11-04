NAME = "дживс"

# фраза (подстрока в нижнем регистре, без знаков препинания) -> ключ команды
PHRASES: list[tuple[str, str]] = [
    ("включи новости", "news_on"),
    ("выключи новости", "news_off"),
    ("отключи новости", "news_off"),
    ("помощь", "help"),
    ("help", "help"),
    ("жетон", "token"),
    ("токен", "token"),
    ("шут", "wowlol"),
    ("смеятьс", "wowlol"),
    ("wowlol", "wowlol"),
    ("фап", "wowfap"),
    ("fap", "wowfap"),
]

SLASH: dict[str, str] = {
    "start": "help",
    "help": "help",
    "news_on": "news_on",
    "news_off": "news_off",
    "token": "token",
    "joke": "wowlol",
    "wowlol": "wowlol",
    "fap": "wowfap",
    "wowfap": "wowfap",
}

_PUNCTUATION = str.maketrans("", "", ",?.!")


def parse_command(text: str | None, chat_id: int, bot_name: str) -> str | None:
    """Ключ команды для сообщения, адресованного боту; None, если сообщение боту не адресовано."""
    if text is None or not text.strip():
        return None
    lowered = text.strip().lower()

    if lowered.startswith("/"):
        token = lowered.split()[0][1:]
        command, _, target = token.partition("@")
        if target and target != bot_name.lower():
            return None
        return SLASH.get(command, "unknown")

    addressed = lowered.startswith(NAME)
    if addressed:
        lowered = lowered[len(NAME):]
    elif chat_id < 0:
        return None

    phrase = " ".join(lowered.translate(_PUNCTUATION).split())
    for known, key in PHRASES:
        if known in phrase:
            return key
    return "unknown"
