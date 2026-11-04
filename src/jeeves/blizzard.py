import base64
import time
from collections.abc import Callable

import aiohttp

TOKEN_URL = "https://oauth.battle.net/token"
TOKEN_INDEX_URL = "https://eu.api.blizzard.com/data/wow/token/index"
TIMEOUT = aiohttp.ClientTimeout(total=15)
EXPIRY_MARGIN = 60


class BlizzardError(Exception):
    """Не удалось получить данные от Blizzard API."""


class BlizzardClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._basic_auth = {"Authorization": f"Basic {basic}"}
        self._clock = clock
        self._access_token: str | None = None
        self._expires_at = 0.0

    async def _token(self) -> str:
        if self._access_token and self._clock() < self._expires_at:
            return self._access_token
        try:
            async with self._session.post(
                TOKEN_URL, data={"grant_type": "client_credentials"}, headers=self._basic_auth, timeout=TIMEOUT
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._access_token = data["access_token"]
            self._expires_at = self._clock() + int(data["expires_in"]) - EXPIRY_MARGIN
        except Exception as error:
            raise BlizzardError("не удалось получить токен доступа") from error
        return self._access_token

    async def get_token_price(self) -> int:
        """Цена жетона WoW в EU, в меди."""
        access_token = await self._token()
        try:
            async with self._session.get(
                TOKEN_INDEX_URL,
                params={"namespace": "dynamic-eu", "locale": "ru_RU"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=TIMEOUT,
            ) as response:
                response.raise_for_status()
                data = await response.json()
            return int(data["price"])
        except Exception as error:
            self._access_token = None  # токен мог быть отозван: в следующий раз получим новый
            raise BlizzardError("не удалось получить цену жетона") from error
