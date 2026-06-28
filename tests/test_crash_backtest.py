from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.market_data import latest_complete_candles, load_candle_snapshot, save_candle_snapshot
from huntbot.models import Candle


def make_candle(timestamp: datetime, price: str = "100", *, unit: int = 5) -> Candle:
    value = Decimal(price)
    return Candle(
        market="KRW-HUNT",
        unit=unit,
        timestamp=timestamp,
        open=value,
        high=value + Decimal("2"),
        low=value - Decimal("3"),
        close=value + Decimal("1"),
        volume=Decimal("123.456"),
    )


def test_candle_snapshot_round_trip_preserves_values(tmp_path):
    candles = [make_candle(datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc), "127.25")]
    path = tmp_path / "candles.csv"

    save_candle_snapshot(candles, path)

    assert load_candle_snapshot(path) == candles


def test_latest_complete_candles_excludes_partial_future_and_old_candles():
    now = datetime(2026, 6, 29, 0, 3, tzinfo=timezone.utc)
    candles = [
        make_candle(now - timedelta(days=184)),
        make_candle(now - timedelta(days=182, minutes=3)),
        make_candle(datetime(2026, 6, 28, 23, 55, tzinfo=timezone.utc)),
        make_candle(datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc)),
        make_candle(datetime(2026, 6, 29, 0, 5, tzinfo=timezone.utc)),
    ]

    result = latest_complete_candles(candles, now=now, days=183)

    assert [item.timestamp for item in result] == [
        now - timedelta(days=182, minutes=3),
        datetime(2026, 6, 28, 23, 55, tzinfo=timezone.utc),
    ]
