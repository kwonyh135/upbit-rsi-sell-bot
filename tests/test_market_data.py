from datetime import datetime, timedelta, timezone

from huntbot.market_data import fetch_latest_candles, latest_completed_candle


class CandleClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_minute_candles(self, market, *, unit, count=200, to=None):
        self.calls.append((market, unit, count, to))
        return self.payload


def raw_candle(timestamp, price=100):
    return {
        "market": "KRW-HUNT",
        "candle_date_time_utc": timestamp,
        "opening_price": price,
        "high_price": price + 1,
        "low_price": price - 1,
        "trade_price": price,
        "candle_acc_trade_volume": 1,
    }


def test_fetch_latest_candles_requests_exact_count_and_sorts():
    client = CandleClient(
        [
            raw_candle("2026-06-09T03:01:00", 101),
            raw_candle("2026-06-09T03:00:00", 100),
        ]
    )

    result = fetch_latest_candles(client, "KRW-HUNT", unit=1, count=2)

    assert client.calls == [("KRW-HUNT", 1, 2, None)]
    assert [item.close for item in result] == [100, 101]


def test_latest_completed_candle_skips_current_five_minute_bucket():
    now = datetime(2026, 6, 9, 3, 7, tzinfo=timezone.utc)
    client = CandleClient(
        [
            raw_candle("2026-06-09T03:05:00", 105),
            raw_candle("2026-06-09T03:00:00", 100),
            raw_candle("2026-06-09T02:55:00", 95),
        ]
    )
    items = fetch_latest_candles(client, "KRW-HUNT", unit=5, count=3)

    completed = latest_completed_candle(items, unit=5, now=now)

    assert completed.timestamp == datetime(2026, 6, 9, 3, 0, tzinfo=timezone.utc)


def test_latest_completed_candle_returns_none_when_all_are_open():
    now = datetime(2026, 6, 9, 3, 2, tzinfo=timezone.utc)
    client = CandleClient([raw_candle("2026-06-09T03:00:00", 100)])
    items = fetch_latest_candles(client, "KRW-HUNT", unit=5, count=1)

    assert latest_completed_candle(items, unit=5, now=now) is None
