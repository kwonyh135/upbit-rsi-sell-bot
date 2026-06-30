from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.crash_backtest import ProtectionConfig
from huntbot.intrabar_backtest import TimingBacktestConfig, run_timing_backtest
from huntbot.intrabar_signals import TimingMode
from huntbot.second_data import SecondCandle


D = Decimal


def utc(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)


def second(timestamp: datetime, price: str) -> SecondCandle:
    value = D(price)
    return SecondCandle(
        market="KRW-HUNT",
        timestamp=timestamp,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=D("1"),
    )


def threshold_fixture(*, signal_price: str, next_price: str) -> list[SecondCandle]:
    start = utc("2026-06-29T22:45:00")
    warmup = [*range(114, 100, -1), 114]
    candles = [
        second(start + timedelta(minutes=5 * index), str(price))
        for index, price in enumerate(warmup)
    ]
    candles.extend(
        [
            second(utc("2026-06-30T00:00:10"), signal_price),
            second(utc("2026-06-30T00:00:11"), next_price),
        ]
    )
    return candles


def config(mode: TimingMode) -> TimingBacktestConfig:
    return TimingBacktestConfig(mode=mode)


def completed_signal_fixture() -> list[SecondCandle]:
    seconds = threshold_fixture(signal_price="100", next_price="100")[:-1]
    seconds.extend(
        [
            second(utc("2026-06-30T00:05:00"), "101"),
            second(utc("2026-06-30T00:05:07"), "102"),
        ]
    )
    return seconds


def hold_gap_fixture() -> list[SecondCandle]:
    seconds = threshold_fixture(signal_price="100", next_price="100")[:-2]
    seconds.extend(
        [
            second(utc("2026-06-30T00:01:10"), "100"),
            second(utc("2026-06-30T00:02:05"), "102"),
        ]
    )
    return seconds


def false_buy_fixture() -> list[SecondCandle]:
    seconds = threshold_fixture(signal_price="100", next_price="102")
    seconds.extend(
        [
            second(utc("2026-06-30T00:04:59"), "114"),
            second(utc("2026-06-30T00:05:00"), "114"),
        ]
    )
    return seconds


def crash_fixture() -> list[SecondCandle]:
    seconds = threshold_fixture(signal_price="100", next_price="100")[:-2]
    seconds.extend(
        [
            second(utc("2026-06-30T00:00:10"), "100"),
            second(utc("2026-06-30T00:00:40"), "100"),
            second(utc("2026-06-30T00:05:00"), "100"),
            second(utc("2026-06-30T00:05:01"), "100"),
            second(utc("2026-06-30T00:10:00"), "93"),
            second(utc("2026-06-30T00:15:00"), "92"),
            second(utc("2026-06-30T00:20:00"), "92"),
            second(utc("2026-06-30T00:20:01"), "91"),
        ]
    )
    return seconds


def protected_config(mode: TimingMode) -> TimingBacktestConfig:
    return TimingBacktestConfig(
        mode=mode,
        protection=ProtectionConfig(
            family="fixed",
            name="fixed-6-12-two-candle",
            high_window_bars=3,
            high_drop_pct=D("6"),
            average_loss_pct=D("12"),
            confirmations=2,
        ),
    )


def test_signal_fills_on_next_observed_trade_with_adverse_slippage():
    seconds = threshold_fixture(signal_price="100", next_price="102")
    result = run_timing_backtest(
        seconds,
        TimingBacktestConfig(
            mode=TimingMode.IMMEDIATE,
            fee_rate=D("0.0005"),
            slippage_rate=D("0.0005"),
        ),
    )

    trade = result.trades[0]
    assert trade.signal_price == D("100")
    assert trade.market_price == D("102")
    assert trade.execution_price == D("102") * D("1.0005")
    assert trade.timestamp > trade.signal_timestamp


def test_completed_mode_cannot_fill_at_signal_candle_close():
    result = run_timing_backtest(completed_signal_fixture(), config(TimingMode.COMPLETED))

    assert result.trades[0].timestamp == utc("2026-06-30T00:05:07")
    assert result.trades[0].signal_timestamp == utc("2026-06-30T00:05:00")


def test_held_signal_matures_during_gap_but_fills_at_next_trade():
    result = run_timing_backtest(hold_gap_fixture(), config(TimingMode.HOLD_30S))

    assert result.trades[0].signal_timestamp == utc("2026-06-30T00:01:40")
    assert result.trades[0].timestamp == utc("2026-06-30T00:02:05")


def test_intrabar_signal_is_false_when_close_no_longer_meets_its_threshold():
    result = run_timing_backtest(false_buy_fixture(), config(TimingMode.IMMEDIATE))

    assert result.false_intrabar_signals == 1


def test_same_completed_crash_rule_applies_to_every_timing_mode():
    results = [
        run_timing_backtest(crash_fixture(), protected_config(mode))
        for mode in TimingMode
    ]

    assert [item.emergency_exits for item in results] == [1, 1, 1]
    assert all(
        any(trade.action == "emergency_sell" for trade in item.trades)
        for item in results
    )
