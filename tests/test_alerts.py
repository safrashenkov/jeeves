from jeeves.alerts import AdminNotifier


async def test_notifier_rate_limits_and_resumes():
    sent: list[str] = []
    now = [1000.0]

    async def send(text: str) -> None:
        sent.append(text)

    notifier = AdminNotifier(send, interval=3600, clock=lambda: now[0])

    assert await notifier.notify("first") is True
    now[0] += 10
    assert await notifier.notify("second") is False
    now[0] += 3600
    assert await notifier.notify("third") is True

    assert sent == ["first", "third"]
