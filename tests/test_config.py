from jeeves.config import Settings


def test_urls_built_from_env(monkeypatch):
    env = {
        "BOT_TOKEN": "1:a",
        "BOT_NAME": "jeeves_bot",
        "ADMIN_ID": "5",
        "WEBHOOK_BASE_URL": "https://jeeves.perm-bear.ru",
        "WEBHOOK_SECRET": "s",
        "DB_USER": "u",
        "DB_PASSWORD": "p@ss/word",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.webhook_url == "https://jeeves.perm-bear.ru/webhook"
    assert "p%40ss%2Fword" in settings.db_url
    assert settings.db_url.startswith("mysql+aiomysql://u:")
    assert settings.db_url.endswith("/wa?charset=utf8mb4")
