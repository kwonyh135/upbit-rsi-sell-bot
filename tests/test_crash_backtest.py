from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.crash_backtest import run_crash_backtest, select_strategy_action
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


def test_strategy_selection_matches_production_phase_rules():
    assert select_strategy_action("buy_2", 65.0, Decimal("10"), Decimal("1000")) == "sell_2"
    assert select_strategy_action("buy_2", 44.0, Decimal("10"), Decimal("1000")) is None
    assert select_strategy_action("buy_2", 40.0, Decimal("10"), Decimal("1000")) == "buy_2"
    assert select_strategy_action("sell_2", 62.0, Decimal("10"), Decimal("1000")) is None
    assert select_strategy_action("sell_1", 62.0, Decimal("10"), Decimal("1000")) == "sell_1"
    assert select_strategy_action("sell_2", 44.0, Decimal("10"), Decimal("1000")) == "buy_1"


def test_rsi_signal_executes_at_next_candle_open():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [make_candle(start + timedelta(minutes=5 * index), "100") for index in range(15)]
    signal = make_candle(start + timedelta(minutes=75), "200")
    next_candle = make_candle(start + timedelta(minutes=80), "180")
    next_candle = Candle(
        market=next_candle.market,
        unit=next_candle.unit,
        timestamp=next_candle.timestamp,
        open=Decimal("150"),
        high=next_candle.high,
        low=next_candle.low,
        close=next_candle.close,
        volume=next_candle.volume,
    )

    result = run_crash_backtest(
        candles + [signal, next_candle],
        protection=None,
        recovery=None,
        fee_rate=Decimal("0"),
        normal_slippage_rate=Decimal("0"),
        crash_slippage_rate=Decimal("0"),
    )

    assert result.events[0].action == "sell_2"
    assert result.events[0].signal_timestamp == signal.timestamp
    assert result.events[0].timestamp == next_candle.timestamp
    assert result.events[0].price == Decimal("150")


def test_backtest_costs_reduce_final_value():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = ["100"] * 15 + ["200", "180"]
    candles = [make_candle(start + timedelta(minutes=5 * index), close) for index, close in enumerate(closes)]
    no_cost = run_crash_backtest(
        candles,
        protection=None,
        recovery=None,
        fee_rate=Decimal("0"),
        normal_slippage_rate=Decimal("0"),
        crash_slippage_rate=Decimal("0"),
    )
    with_cost = run_crash_backtest(
        candles,
        protection=None,
        recovery=None,
        fee_rate=Decimal("0.0005"),
        normal_slippage_rate=Decimal("0.0005"),
        crash_slippage_rate=Decimal("0.003"),
    )

    assert with_cost.final_value < no_cost.final_value
