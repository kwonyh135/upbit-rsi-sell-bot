from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from huntbot.crash_backtest import ProtectionConfig
import huntbot.intrabar_backtest as intrabar_backtest
from huntbot.intrabar_backtest import TimingBacktestConfig, run_timing_backtest
from huntbot.intrabar_signals import TimedSignal, TimingMode
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


def fill_action(
    action: str,
    state: intrabar_backtest.PortfolioState,
    *,
    fee_rate: str = "0",
) -> tuple[intrabar_backtest.PortfolioState, intrabar_backtest.TimingTrade]:
    timestamp = utc("2026-06-30T00:00:00")
    pending = intrabar_backtest.PendingSignal(
        TimedSignal(action, timestamp, timestamp, 50.0),
        D("10"),
    )
    return intrabar_backtest._fill_signal(
        state,
        pending,
        second(timestamp + timedelta(seconds=1), "10"),
        TimingBacktestConfig(
            mode=TimingMode.IMMEDIATE,
            fee_rate=D(fee_rate),
            slippage_rate=D("0"),
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


def test_completed_mode_fills_on_first_trade_after_candle_boundary():
    result = run_timing_backtest(completed_signal_fixture(), config(TimingMode.COMPLETED))

    assert result.trades[0].timestamp == utc("2026-06-30T00:05:00")
    assert result.trades[0].signal_timestamp == utc("2026-06-30T00:05:00")


def test_held_signal_matures_during_gap_but_fills_at_next_trade():
    result = run_timing_backtest(hold_gap_fixture(), config(TimingMode.HOLD_30S))

    assert result.trades[0].signal_timestamp == utc("2026-06-30T00:01:40")
    assert result.trades[0].timestamp == utc("2026-06-30T00:02:05")


def test_intrabar_signal_is_false_when_close_no_longer_meets_its_threshold():
    result = run_timing_backtest(false_buy_fixture(), config(TimingMode.IMMEDIATE))

    assert result.false_intrabar_signals == 1


def test_completed_crash_rule_can_trigger_for_every_timing_mode():
    results = [
        run_timing_backtest(crash_fixture(), protected_config(mode))
        for mode in TimingMode
    ]

    assert all(item.emergency_exits >= 1 for item in results)
    assert all(
        any(trade.action == "emergency_sell" for trade in item.trades)
        for item in results
    )


def test_unfinished_final_bucket_is_included_in_maximum_drawdown():
    seconds = threshold_fixture(signal_price="100", next_price="100")
    seconds.append(second(utc("2026-06-30T00:04:59"), "10"))

    result = run_timing_backtest(seconds, config(TimingMode.IMMEDIATE))

    expected = (D("3000000") - result.final_value) / D("3000000") * D("100")
    assert result.max_drawdown_pct == expected


def test_maximum_drawdown_marks_every_observed_second():
    seconds = threshold_fixture(signal_price="100", next_price="100")
    seconds.extend(
        [
            second(utc("2026-06-30T00:01:00"), "50"),
            second(utc("2026-06-30T00:04:59"), "100"),
        ]
    )

    result = run_timing_backtest(seconds, config(TimingMode.IMMEDIATE))

    assert result.max_drawdown_pct > D("20")


def test_backtest_records_only_flat_to_invested_to_flat_cycles(monkeypatch):
    start = utc("2026-06-30T00:00:00")
    actions = {
        start: "buy_1",
        start + timedelta(seconds=1): "buy_2",
        start + timedelta(seconds=2): "sell_1",
        start + timedelta(seconds=3): "sell_2",
    }

    def scripted_signal(*, timestamp, candle_start, tracker, **kwargs):
        action = actions.get(timestamp)
        signal = (
            TimedSignal(action, timestamp, candle_start, 50.0)
            if action is not None
            else None
        )
        return signal, tracker

    monkeypatch.setattr(intrabar_backtest, "observe_signal", scripted_signal)
    seconds = [
        second(start + timedelta(seconds=index), str(100 + index))
        for index in range(5)
    ]

    result = run_timing_backtest(
        seconds,
        TimingBacktestConfig(
            mode=TimingMode.IMMEDIATE,
            fee_rate=D("0"),
            slippage_rate=D("0"),
        ),
    )

    assert len(result.cycles) == 1
    cycle = result.cycles[0]
    assert cycle.start_timestamp == start + timedelta(seconds=1)
    assert cycle.end_timestamp == start + timedelta(seconds=4)
    assert cycle.start_value == D("3000000")
    assert cycle.end_value == result.final_cash
    assert cycle.pnl == cycle.end_value - cycle.start_value


def test_fill_rejects_an_unsupported_action():
    timestamp = utc("2026-06-30T00:00:00")
    state = intrabar_backtest.PortfolioState(D("0"), D("10"), D("100"), "sell_1")
    pending = intrabar_backtest.PendingSignal(
        TimedSignal("hold", timestamp, timestamp, 50.0),
        D("100"),
    )

    with pytest.raises(ValueError, match="unsupported action: hold"):
        intrabar_backtest._fill_signal(
            state,
            pending,
            second(timestamp + timedelta(seconds=1), "100"),
            config(TimingMode.IMMEDIATE),
        )


def test_buy_fee_is_reserved_inside_spend_and_sell_fee_reduces_proceeds():
    bought_state, buy_trade = fill_action(
        "buy_1",
        intrabar_backtest.PortfolioState(D("1000"), D("0"), D("0"), "buy_1"),
        fee_rate="0.1",
    )
    sold_state, sell_trade = fill_action(
        "sell_1",
        intrabar_backtest.PortfolioState(D("0"), D("10"), D("10"), "sell_1"),
        fee_rate="0.1",
    )

    assert bought_state.cash == D("500")
    assert buy_trade.quantity == D("500") / D("1.1") / D("10")
    assert sold_state.cash == D("5") * D("10") * D("0.9")
    assert sell_trade.remaining_quantity == D("5")


@pytest.mark.parametrize(
    ("action", "state", "expected_phase"),
    [
        ("buy_1", intrabar_backtest.PortfolioState(D("100"), D("0"), D("0"), "buy_1"), "buy_2"),
        ("buy_2", intrabar_backtest.PortfolioState(D("100"), D("1"), D("10"), "buy_2"), "sell_1"),
        ("sell_1", intrabar_backtest.PortfolioState(D("0"), D("10"), D("10"), "sell_1"), "sell_2"),
        ("sell_2", intrabar_backtest.PortfolioState(D("0"), D("10"), D("10"), "sell_2"), "buy_1"),
    ],
)
def test_normal_fill_advances_to_its_production_phase(action, state, expected_phase):
    next_state, trade = fill_action(action, state)

    assert next_state.phase == expected_phase
    assert trade.phase == expected_phase


def test_average_loss_requires_two_completed_confirmations_without_high_drop():
    protection = ProtectionConfig(
        family="fixed",
        name="average-loss-only",
        high_window_bars=3,
        high_drop_pct=D("100"),
        average_loss_pct=D("6"),
        confirmations=2,
    )

    result = run_timing_backtest(
        crash_fixture(),
        TimingBacktestConfig(mode=TimingMode.IMMEDIATE, protection=protection),
    )

    emergency = [trade for trade in result.trades if trade.action == "emergency_sell"]
    assert len(emergency) == 1
    assert emergency[0].signal_timestamp == utc("2026-06-30T00:20:00")
    assert emergency[0].timestamp == utc("2026-06-30T00:20:00")


def test_timing_backtest_does_not_call_full_history_provisional_rsi(monkeypatch):
    def reject_full_history(*args, **kwargs):
        raise AssertionError("full-history provisional_rsi called")

    monkeypatch.setattr("huntbot.intrabar_signals.provisional_rsi", reject_full_history)
    assert not hasattr(intrabar_backtest, "provisional_rsi")

    run_timing_backtest(
        threshold_fixture(signal_price="100", next_price="102"),
        config(TimingMode.IMMEDIATE),
    )
