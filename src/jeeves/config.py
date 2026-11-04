from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    bot_name: str
    admin_id: int
    webhook_base_url: str
    webhook_path: str = "/webhook"
    webhook_secret: str
    listen_host: str = "127.0.0.1"
    listen_port: int = 18090
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str
    db_password: str
    db_name: str = "wa"
    news_interval_seconds: int = 300

    @property
    def webhook_url(self) -> str:
        return self.webhook_base_url.rstrip("/") + self.webhook_path

    @property
    def db_url(self) -> str:
        password = quote(self.db_password, safe="")
        return (
            f"mysql+aiomysql://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
