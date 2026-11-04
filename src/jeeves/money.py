def format_gold(copper: int) -> str:
    """Цена в меди -> «245 000 г» (серебро и медь отбрасываются)."""
    return f"{copper // 10_000:,}".replace(",", " ") + " г"
