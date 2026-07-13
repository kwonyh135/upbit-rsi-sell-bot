from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.intrabar_backtest import TimingBacktestResult
from huntbot.intrabar_signals import TimingMode
from huntbot.intrabar_study import SLIPPAGES, run_timing_study, study_config
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


def test_protected_preset_matches_live_rule_exactly():
    protection = study_config(TimingMode.COMPLETED, D("0.0005"), protected=True).protection

    assert protection is not None
    assert protection.high_window_bars == 1
    assert protection.high_drop_pct == D("6")
    assert protection.average_loss_pct == D("12")
    assert protection.confirmations == 2


def test_split_uses_exact_boundary_and_independent_lists(monkeypatch):
    datasets = []
    monkeypatch.setattr(
        "huntbot.intrabar_study.run_timing_backtest",
        lambda candles, config: datasets.append(candles) or fake_result(config),
    )

    study = run_timing_study(sample_seconds())

    start = sample_seconds()[0].timestamp
    assert study.split_at == start + timedelta(days=2)
    assert [item.timestamp for item in datasets[18]] == [
        start,
        start + timedelta(days=1),
    ]
    assert [item.timestamp for item in datasets[36]] == [
        start + timedelta(days=2),
        start + timedelta(days=3),
    ]
    assert datasets[0] is not datasets[18]
    assert datasets[18] is not datasets[36]
