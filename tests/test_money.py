from jeeves.money import format_gold


def test_format_gold_groups_thousands_and_drops_silver_copper():
    assert format_gold(2_450_000_000) == "245 000 г"
    assert format_gold(2_450_099_999) == "245 009 г"
    assert format_gold(9_999) == "0 г"
    assert format_gold(10_000) == "1 г"
