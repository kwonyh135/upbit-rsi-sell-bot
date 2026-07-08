from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.btc_futures import StrategyKind
from huntbot.btc_rsi_optimization import (
    RsiThresholds,
    classify_optimization_conclusion,
    generate_threshold_grid,
    optimize_btc_rsi,
    optimization_to_json,
)
from huntbot.models import Candle


UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)


def candle_at(index: int, price: str) -> Candle:
    value = Decimal(price)
    return Candle("BTCUSDT", 5, START + timedelta(minutes=5 * index), value, value, value, value, Decimal("1"))


def test_threshold_grid_keeps_ordered_two_step_rules_and_can_disable_shorts():
    grid = generate_threshold_grid(long_entries=(45,), long_exits=(60,), short_entries=(60,), short_exits=(45,))

    assert grid == (
        RsiThresholds(long_entry_1=45, long_entry_2=40, long_exit_1=60, long_exit_2=65, short_entry_1=60, short_entry_2=65, short_exit_1=45, short_exit_2=40),
    )
    assert generate_threshold_grid(long_entries=(45,), long_exits=(60,), include_shorts=False)[0].short_entry_1 is None


def test_optimizer_selects_holdout_winner_and_includes_long_only_candidates():
    candles = [candle_at(i, str(100 + i)) for i in range(80)]
    thresholds = (
        RsiThresholds(45, 40, 60, 65, None, None, None, None),
        RsiThresholds(35, 30, 70, 75, 70, 75, 35, 30),
    )
    forced_rsi = {item.timestamp: (44.0 if i % 12 == 0 else 66.0 if i % 12 == 6 else 50.0) for i, item in enumerate(candles)}

    study = optimize_btc_rsi(
        candles,
        [],
        START,
        START + timedelta(minutes=5 * 80),
        thresholds=thresholds,
        rsi_values=forced_rsi,
        holdout_start=START + timedelta(minutes=5 * 50),
    )

    assert {candidate.kind for candidate in study.candidates} >= {StrategyKind.LONG_ONLY, StrategyKind.BIDIRECTIONAL}
    assert study.selected.kind == StrategyKind.LONG_ONLY
    assert study.selected.holdout.result.return_pct == max(item.holdout.result.return_pct for item in study.candidates)
    assert study.conclusion in {"not recommended", "inconclusive", "recommended for further paper trading"}


def test_optimization_json_is_ascii_and_contains_selected_thresholds():
    candles = [candle_at(i, "100") for i in range(30)]
    forced_rsi = {item.timestamp: 50.0 for item in candles}
    study = optimize_btc_rsi(
        candles,
        [],
        START,
        START + timedelta(minutes=5 * 30),
        thresholds=(RsiThresholds(45, 40, 60, 65, None, None, None, None),),
        rsi_values=forced_rsi,
        holdout_start=START + timedelta(minutes=5 * 20),
    )

    payload = optimization_to_json(study, {"market": "BTCUSDT"})

    assert '"selected"' in payload
    assert '"long_entry_1": 45' in payload
    assert "BTCUSDT" in payload


def test_optimizer_reuses_calculated_rsi_values(monkeypatch):
    import huntbot.btc_rsi_optimization as opt

    calls = []
    candles = [candle_at(i, str(100 + i % 4)) for i in range(35)]

    def fake_rsi(closes, period=14):
        calls.append(len(closes))
        return [None if index < 14 else 50.0 for index, _ in enumerate(closes)]

    monkeypatch.setattr(opt, "rsi", fake_rsi)

    opt.optimize_btc_rsi(
        candles,
        [],
        START,
        START + timedelta(minutes=5 * 35),
        thresholds=(
            RsiThresholds(45, 40, 60, 65, None, None, None, None),
            RsiThresholds(40, 35, 65, 70, None, None, None, None),
        ),
        holdout_start=START + timedelta(minutes=5 * 25),
    )

    assert calls == [35]


def test_optimizer_shortlists_candidates_before_expensive_full_runs():
    candles = [candle_at(i, str(100 + i % 7)) for i in range(60)]
    thresholds = tuple(
        RsiThresholds(entry, entry - 5, 60, 65, None, None, None, None)
        for entry in (30, 35, 40, 45, 50)
    )

    study = optimize_btc_rsi(
        candles,
        [],
        START,
        START + timedelta(minutes=5 * 60),
        thresholds=thresholds,
        rsi_values={item.timestamp: 44.0 if i % 9 == 0 else 66.0 if i % 9 == 4 else 50.0 for i, item in enumerate(candles)},
        holdout_start=START + timedelta(minutes=5 * 40),
        shortlist_size=2,
    )

    assert len(study.candidates) == 2


def test_optimization_conclusion_downgrades_negative_development_or_full_result():
    conclusion, reasons = classify_optimization_conclusion(
        base_conclusion="recommended for further paper trading",
        base_reasons=(),
        development_return=Decimal("-1"),
        full_return=Decimal("-2"),
    )

    assert conclusion == "inconclusive"
    assert "negative development return" in reasons
    assert "negative full-period return" in reasons
