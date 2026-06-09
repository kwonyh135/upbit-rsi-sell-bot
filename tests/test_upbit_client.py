from huntbot.upbit_client import UpbitClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "response text"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.text)


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers, timeout))
        return FakeResponse([])

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers, timeout))
        return FakeResponse({"uuid": "order-1"})


def test_public_candles_do_not_include_auth_header():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="s" * 32, session=session)
    client.get_minute_candles("KRW-HUNT", unit=60, count=2)
    method, url, params, headers, timeout = session.calls[0]
    assert method == "GET"
    assert url.endswith("/v1/candles/minutes/60")
    assert params["market"] == "KRW-HUNT"
    assert headers is None


def test_market_sell_uses_ask_market_volume():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="s" * 32, session=session)
    client.market_sell("KRW-HUNT", "123.45")
    method, url, body, headers, timeout = session.calls[0]
    assert method == "POST"
    assert body == {"market": "KRW-HUNT", "side": "ask", "ord_type": "market", "volume": "123.45"}
    assert headers["Authorization"].startswith("Bearer ")


def test_market_buy_uses_bid_price_amount():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="s" * 32, session=session)
    client.market_buy("KRW-HUNT", "50000")
    method, url, body, headers, timeout = session.calls[0]
    assert method == "POST"
    assert body == {"market": "KRW-HUNT", "side": "bid", "ord_type": "price", "price": "50000"}
    assert headers["Authorization"].startswith("Bearer ")


def test_market_orders_include_optional_identifier():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="s" * 32, session=session)

    client.market_sell("KRW-HUNT", "10", identifier="huntbot-sell-1")
    client.market_buy("KRW-HUNT", "5000", identifier="huntbot-buy-1")

    assert session.calls[0][2]["identifier"] == "huntbot-sell-1"
    assert session.calls[1][2]["identifier"] == "huntbot-buy-1"


def test_get_order_uses_uuid_or_identifier():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="s" * 32, session=session)

    client.get_order(uuid="order-1")
    client.get_order(identifier="huntbot-buy-1")

    assert session.calls[0][2] == {"uuid": "order-1"}
    assert session.calls[1][2] == {"identifier": "huntbot-buy-1"}
