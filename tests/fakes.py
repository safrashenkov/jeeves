"""Подмены aiohttp.ClientSession для тестов без сети."""


class FakeResponse:
    def __init__(self, body: bytes | dict):
        self._body = body

    def raise_for_status(self):
        pass

    async def read(self) -> bytes:
        return self._body

    async def json(self) -> dict:
        return self._body


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
    """outcomes: url -> ответ (bytes/dict), исключение или список таких значений (по одному на вызов)."""

    def __init__(self, outcomes: dict):
        self._outcomes = {url: (list(v) if isinstance(v, list) else [v]) for url, v in outcomes.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def _request(self, method: str, url: str, kwargs: dict) -> FakeRequest:
        self.calls.append((method, url, kwargs))
        queue = self._outcomes[url]
        return FakeRequest(queue.pop(0) if len(queue) > 1 else queue[0])

    def get(self, url, **kwargs):
        return self._request("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._request("POST", url, kwargs)
