from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.btc_futures import StrategyKind
from huntbot.btc_futures_study import classify_conclusion, run_btc_futures_study
from huntbot.models import Candle


UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 7, 1, tzinfo=UTC)


def candle_at(timestamp: datetime, price: Decimal) -> Candle:
    return Candle("BTCUSDT", 5, timestamp, price, price, price, price, Decimal("1"))


def test_study_runs_all_strategies_and_slippage_scenarios_on_each_segment():
    candles = [candle_at(START + timedelta(minutes=5 * i), Decimal("100") + Decimal(i % 20)) for i in range(40)]
    end = candles[-1].timestamp + timedelta(minutes=5)
    study = run_btc_futures_study(candles, [], START, end, holdout_start=candles[25].timestamp)

    assert len(study.full_runs) == 18
    assert len(study.development_runs) == 18
    assert len(study.holdout_runs) == 18
    assert {run.result.config.slippage for run in study.full_runs} == {
        Decimal("0.0002"), Decimal("0.0005"), Decimal("0.001")
    }
    assert {run.result.config.kind for run in study.full_runs} == set(StrategyKind)


def test_holdout_starts_after_four_complete_months():
    candles = [candle_at(START + timedelta(days=30 * i), Decimal("100")) for i in range(7)]
    study = run_btc_futures_study(candles, [], START, END, allow_sparse=True)
    assert study.holdout_start == datetime(2026, 5, 1, tzinfo=UTC)


def test_conclusion_gates_never_recommend_immediate_live_trading():
    stable = classify_conclusion(
        holdout_return=Decimal("5"), holdout_mdd=Decimal("10"), stress_return=Decimal("1"),
        cycles=12, profit_concentration=Decimal("20"), buy_hold_return=Decimal("2"), buy_hold_mdd=Decimal("12"),
    )
    negative = classify_conclusion(
        holdout_return=Decimal("-1"), holdout_mdd=Decimal("10"), stress_return=Decimal("1"),
        cycles=12, profit_concentration=Decimal("20"), buy_hold_return=Decimal("2"), buy_hold_mdd=Decimal("12"),
    )
    thin = classify_conclusion(
        holdout_return=Decimal("5"), holdout_mdd=Decimal("10"), stress_return=Decimal("1"),
        cycles=3, profit_concentration=Decimal("20"), buy_hold_return=Decimal("2"), buy_hold_mdd=Decimal("12"),
    )

    assert stable[0] == "recommended for further paper trading"
    assert negative[0] == "not recommended"
    assert thin[0] == "inconclusive"
    assert "live" not in stable[0]
