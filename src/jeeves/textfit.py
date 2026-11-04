import html


def fit_escaped(text: str, budget: int) -> str:
    """HTML-экранированный `text`, обрезанный так, чтобы результат был не длиннее `budget` символов.

    Режется исходный текст, а не экранированный, поэтому сущности вроде `&amp;` не разрываются.
    """
    escaped = html.escape(text)
    if len(escaped) <= budget:
        return escaped
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(html.escape(text[:middle])) <= budget:
            low = middle
        else:
            high = middle - 1
    return html.escape(text[:low])
