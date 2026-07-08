from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib

import pytest

from huntbot.models import Candle


START = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)


def _btc():
    return importlib.import_module("huntbot.btc_futures")


def candle_at(
    offset_minutes: int,
    close: str = "100",
    *,
    market: str = "BTCUSDT",
    unit: int = 5,
    volume: str = "1",
    base: datetime = START,
) -> Candle:
    price = Decimal(close)
    return Candle(
        market=market,
        unit=unit,
        timestamp=base + timedelta(minutes=offset_minutes),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(volume),
    )


def synthetic_trend_candles(four_hour_bar_closes: list[str]) -> list[Candle]:
    candles: list[Candle] = []
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    for bar_index, close in enumerate(four_hour_bar_closes):
        for offset in range(48):
            candles.append(candle_at((bar_index * 48 + offset) * 5, close=close, base=base))
    return candles


def test_validate_candles_deduplicates_identical_duplicates_and_counts_warmup_gaps():
    btc = _btc()
    candles = [
        candle_at(-15, close="98"),
        candle_at(-5, close="99"),
        candle_at(0, close="100"),
        candle_at(5, close="101"),
        candle_at(5, close="101"),
        candle_at(10, close="102"),
    ]

    validated, missing_intervals = btc.validate_candles(candles, START, END)

    assert [item.timestamp for item in validated] == [
        START - timedelta(minutes=15),
        START - timedelta(minutes=5),
        START,
        START + timedelta(minutes=5),
        START + timedelta(minutes=10),
    ]
    assert missing_intervals == 1


def test_validate_candles_rejects_conflicting_duplicate():
    btc = _btc()
    candles = [candle_at(0, close="100"), candle_at(0, close="101")]

    with pytest.raises(ValueError, match="conflicting duplicate"):
        btc.validate_candles(candles, START, START + timedelta(minutes=5))


def test_validate_candles_rejects_missing_required_interval():
    btc = _btc()
    candles = [
        candle_at(-5, close="99"),
        candle_at(0, close="100"),
        candle_at(10, close="102"),
    ]

    with pytest.raises(ValueError, match="missing 1 required five-minute interval"):
        btc.validate_candles(candles, START, END)


def test_regime_is_not_visible_until_four_hour_bar_closes():
    btc = _btc()
    candles = synthetic_trend_candles((["100"] * 200) + ["200", "200"])

    regimes = btc.classify_regimes(candles)

    jump_bar_start = candles[200 * 48].timestamp
    post_close_boundary = candles[201 * 48].timestamp
    assert regimes[jump_bar_start - timedelta(minutes=5)] == btc.Regime.NEUTRAL
    assert regimes[jump_bar_start] == btc.Regime.NEUTRAL
    assert regimes[post_close_boundary] == btc.Regime.BULL
