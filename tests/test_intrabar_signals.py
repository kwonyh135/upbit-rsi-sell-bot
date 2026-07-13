from datetime import datetime, timezone
from decimal import Decimal

from huntbot.indicators import rsi
from huntbot.intrabar_signals import (
    SignalTracker,
    TimingMode,
    aggregate_five_minute_bars,
    mature_held_signal,
    observe_signal,
    provisional_rsi,
    threshold_action,
)
from huntbot.second_data import SecondCandle


def utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)


def second(
    timestamp: str,
    close: str,
    *,
    high: str | None = None,
    low: str | None = None,
    volume: str = "1",
) -> SecondCandle:
    price = Decimal(close)
    return SecondCandle(
        market="KRW-HUNT",
        timestamp=datetime.fromisoformat(timestamp),
        open=price,
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=price,
        volume=Decimal(volume),
    )


def test_aggregate_uses_trade_seconds_and_utc_five_minute_bucket():
    seconds = [
        second("2026-06-30T00:00:10+00:00", "100", high="101", low="99", volume="2"),
        second("2026-06-30T00:04:59+00:00", "105", high="106", low="104", volume="3"),
    ]

    bars = aggregate_five_minute_bars(seconds)

    assert bars[0].timestamp == datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc)
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume) == (
        Decimal("100"),
        Decimal("106"),
        Decimal("99"),
        Decimal("105"),
        Decimal("5"),
    )


def test_provisional_rsi_replaces_only_unfinished_close():
    closes = [Decimal(str(value)) for value in range(100, 115)]

    expected = rsi([float(value) for value in [*closes, Decimal("90")]], period=14)[-1]

    assert provisional_rsi(closes, Decimal("90"), period=14) == expected


def test_threshold_action_uses_approved_sell_levels():
    common = {"phase": "sell_1", "has_hunt": True, "has_krw": False}

    assert threshold_action(rsi_value=55.9, **common) is None
    assert threshold_action(rsi_value=56, **common) == "sell_1"
    assert threshold_action(rsi_value=61, **common) == "sell_2"


def test_immediate_signals_on_first_threshold_crossing():
    signal, tracker = observe_signal(
        mode=TimingMode.IMMEDIATE,
        timestamp=utc("2026-06-30T00:01:10"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.9,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=SignalTracker(),
    )

    assert signal.action == "buy_1"
    assert signal.timestamp == utc("2026-06-30T00:01:10")
    assert tracker.acted_candle == utc("2026-06-30T00:00:00")


def test_hold_requires_thirty_wall_clock_seconds_without_price_update():
    tracker = SignalTracker()

    signal, tracker = observe_signal(
        mode=TimingMode.HOLD_30S,
        timestamp=utc("2026-06-30T00:01:10"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.9,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )

    assert signal is None

    signal, tracker = mature_held_signal(tracker, utc("2026-06-30T00:01:40"))

    assert signal.action == "buy_1"
    assert signal.timestamp == utc("2026-06-30T00:01:40")
    assert tracker.acted_candle == utc("2026-06-30T00:00:00")


def test_hold_resets_when_condition_breaks_before_thirty_seconds():
    tracker = SignalTracker(
        active_action="buy_1",
        active_since=utc("2026-06-30T00:01:10"),
        active_candle=utc("2026-06-30T00:00:00"),
    )

    signal, tracker = observe_signal(
        mode=TimingMode.HOLD_30S,
        timestamp=utc("2026-06-30T00:01:25"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=45.1,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )

    assert signal is None
    assert tracker.active_action is None


def test_hold_preserves_start_time_across_five_minute_rollover():
    tracker = SignalTracker()

    signal, tracker = observe_signal(
        mode=TimingMode.HOLD_30S,
        timestamp=utc("2026-06-30T00:04:50"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.9,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )

    assert signal is None

    signal, tracker = observe_signal(
        mode=TimingMode.HOLD_30S,
        timestamp=utc("2026-06-30T00:05:05"),
        candle_start=utc("2026-06-30T00:05:00"),
        rsi_value=44.8,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )

    assert signal is None
    assert tracker.active_action == "buy_1"
    assert tracker.active_since == utc("2026-06-30T00:04:50")

    signal, tracker = mature_held_signal(tracker, utc("2026-06-30T00:05:20"))

    assert signal is not None
    assert signal.action == "buy_1"
    assert signal.timestamp == utc("2026-06-30T00:05:20")


def test_second_signal_from_same_candle_is_suppressed():
    signal, tracker = observe_signal(
        mode=TimingMode.IMMEDIATE,
        timestamp=utc("2026-06-30T00:01:10"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.9,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=SignalTracker(),
    )

    assert signal is not None

    second_signal, tracker = observe_signal(
        mode=TimingMode.IMMEDIATE,
        timestamp=utc("2026-06-30T00:01:20"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.8,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )

    assert second_signal is None
    assert tracker.acted_candle == utc("2026-06-30T00:00:00")
