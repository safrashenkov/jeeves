import time
from collections.abc import Awaitable, Callable


class AdminNotifier:
    """Шлёт сообщения админу не чаще одного раза в `interval` секунд."""

    def __init__(
        self,
        send: Callable[[str], Awaitable[None]],
        interval: float = 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send = send
        self._interval = interval
        self._clock = clock
        self._last: float | None = None

    async def notify(self, text: str) -> bool:
        now = self._clock()
        if self._last is not None and now - self._last < self._interval:
            return False
        self._last = now
        await self._send(text)
        return True
