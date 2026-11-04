import pytest
from fakes import FakeSession

from jeeves.blizzard import TOKEN_INDEX_URL, TOKEN_URL, BlizzardClient, BlizzardError

AUTH = {"access_token": "abc", "expires_in": 86399}
PRICE = {"last_updated_timestamp": 1, "price": 2_450_000_000}


async def test_token_price_fetches_token_then_price():
    session = FakeSession({TOKEN_URL: AUTH, TOKEN_INDEX_URL: PRICE})
    client = BlizzardClient(session, "id", "secret")

    assert await client.get_token_price() == 2_450_000_000

    (method1, url1, kwargs1), (method2, url2, kwargs2) = session.calls
    assert (method1, url1) == ("POST", TOKEN_URL)
    assert kwargs1["data"] == {"grant_type": "client_credentials"}
    assert (method2, url2) == ("GET", TOKEN_INDEX_URL)
    assert kwargs2["headers"] == {"Authorization": "Bearer abc"}
    assert kwargs2["params"]["namespace"] == "dynamic-eu"


async def test_access_token_is_cached_until_expiry():
    session = FakeSession({TOKEN_URL: [AUTH, {"access_token": "new", "expires_in": 86399}], TOKEN_INDEX_URL: PRICE})
    now = [1000.0]
    client = BlizzardClient(session, "id", "secret", clock=lambda: now[0])

    await client.get_token_price()
    now[0] += 3600
    await client.get_token_price()
    assert [c[0] for c in session.calls].count("POST") == 1

    now[0] += 86400
    await client.get_token_price()
    assert [c[0] for c in session.calls].count("POST") == 2
    assert session.calls[-1][2]["headers"] == {"Authorization": "Bearer new"}


async def test_failures_are_wrapped_in_blizzard_error():
    session = FakeSession({TOKEN_URL: TimeoutError("boom"), TOKEN_INDEX_URL: PRICE})
    client = BlizzardClient(session, "id", "secret")

    with pytest.raises(BlizzardError):
        await client.get_token_price()


async def test_unexpected_price_payload_is_blizzard_error():
    session = FakeSession({TOKEN_URL: AUTH, TOKEN_INDEX_URL: {"nope": 1}})
    client = BlizzardClient(session, "id", "secret")

    with pytest.raises(BlizzardError):
        await client.get_token_price()
