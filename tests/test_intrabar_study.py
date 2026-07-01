from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.intrabar_backtest import TimingBacktestResult
from huntbot.intrabar_signals import TimingMode
from huntbot.intrabar_study import SLIPPAGES, run_timing_study
from huntbot.second_data import SecondCandle


D = Decimal


def sample_seconds() -> list[SecondCandle]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return [
        SecondCandle("KRW-HUNT", start + timedelta(days=index), D("100"), D("100"), D("100"), D("100"), D("1"))
        for index in range(4)
    ]


def fake_result(config) -> TimingBacktestResult:
    return TimingBacktestResult(
        mode=config.mode,
        final_value=config.initial_krw,
        return_pct=D("0"),
        max_drawdown_pct=D("0"),
        false_intrabar_signals=0,
        emergency_exits=0,
        final_cash=config.initial_krw,
        final_quantity=D("0"),
        final_phase="sell_1",
        trades=(),
    )


def test_study_runs_three_modes_two_protection_states_and_three_slippages(monkeypatch):
    calls = []
    datasets = []

    def run(candles, config):
        calls.append(config)
        datasets.append(tuple(item.timestamp for item in candles))
        return fake_result(config)

    monkeypatch.setattr("huntbot.intrabar_study.run_timing_backtest", run)

    study = run_timing_study(sample_seconds())

    assert len(calls) == 54
    assert {call.mode for call in calls} == set(TimingMode)
    assert {call.slippage_rate for call in calls} == set(SLIPPAGES)
    assert {call.protection is None for call in calls} == {True, False}
    assert {call.initial_krw for call in calls} == {D("3000000")}
    assert {len(items) for items in datasets[:18]} == {4}
    assert {len(items) for items in datasets[18:36]} == {2}
    assert {len(items) for items in datasets[36:]} == {2}
    assert study.primary[TimingMode.COMPLETED.value].mode == TimingMode.COMPLETED

