from dataclasses import dataclass


@dataclass(frozen=True)
class Reply:
    """Ответ с медиа. Обычные текстовые ответы обработчики возвращают просто строкой."""

    text: str = ""  # HTML-разметка Telegram
    photo: str | None = None  # URL картинки
    animation: str | None = None  # URL гифки
    spoiler: bool = False  # скрыть медиа под спойлер
