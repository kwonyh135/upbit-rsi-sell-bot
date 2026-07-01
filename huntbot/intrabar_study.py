from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from huntbot.crash_backtest import ProtectionConfig
from huntbot.intrabar_backtest import (
    TimingBacktestConfig,
    TimingBacktestResult,
    run_timing_backtest,
)
from huntbot.intrabar_signals import TimingMode
from huntbot.second_data import SecondCandle


SLIPPAGES = (Decimal("0.0005"), Decimal("0.003"), Decimal("0.01"))
BASE_SLIPPAGE = SLIPPAGES[0]
STRESS_SLIPPAGE = SLIPPAGES[1]


@dataclass(frozen=True)
class TimingStudyResult:
    split_at: datetime
    runs: dict[str, dict[str, TimingBacktestResult]]
    recommendation: str
    recommendation_reason: str

    @property
    def primary(self) -> dict[str, TimingBacktestResult]:
        return {
            mode.value: self.runs["full"][run_key(mode, BASE_SLIPPAGE, protected=True)]
            for mode in TimingMode
        }


def run_key(mode: TimingMode, slippage: Decimal, *, protected: bool) -> str:
    state = "protected" if protected else "unprotected"
    return f"{state}:{slippage}:{mode.value}"


def study_config(
    mode: TimingMode,
    slippage: Decimal,
    *,
    protected: bool,
) -> TimingBacktestConfig:
    protection = None
    if protected:
        protection = ProtectionConfig(
            family="fixed",
            name="fixed-6-12-two-candle",
            high_window_bars=3,
            high_drop_pct=Decimal("6"),
            average_loss_pct=Decimal("12"),
            confirmations=2,
        )
    return TimingBacktestConfig(
        mode=mode,
        slippage_rate=slippage,
        initial_krw=Decimal("3000000"),
        protection=protection,
    )


def run_timing_study(seconds: Sequence[SecondCandle]) -> TimingStudyResult:
    ordered = sorted(seconds, key=lambda item: item.timestamp)
    if len(ordered) < 2:
        raise ValueError("at least two second candles are required")
    split_at = ordered[0].timestamp + (ordered[-1].timestamp - ordered[0].timestamp) * 2 / 3
    datasets = {
        "full": ordered,
        "training": [item for item in ordered if item.timestamp < split_at],
        "holdout": [item for item in ordered if item.timestamp >= split_at],
    }
    if not datasets["training"] or not datasets["holdout"]:
        raise ValueError("chronological split must produce non-empty segments")

    runs: dict[str, dict[str, TimingBacktestResult]] = {}
    for segment, segment_seconds in datasets.items():
        segment_runs = {}
        for protected in (True, False):
            for slippage in SLIPPAGES:
                for mode in TimingMode:
                    config = study_config(mode, slippage, protected=protected)
                    segment_runs[run_key(mode, slippage, protected=protected)] = (
                        run_timing_backtest(segment_seconds, config)
                    )
        runs[segment] = segment_runs

    recommendation, reason = evaluate_recommendation(runs)
    return TimingStudyResult(split_at, runs, recommendation, reason)


def evaluate_recommendation(
    runs: dict[str, dict[str, TimingBacktestResult]],
) -> tuple[str, str]:
    holdout = runs["holdout"]
    completed = holdout[run_key(TimingMode.COMPLETED, BASE_SLIPPAGE, protected=True)]
    candidates = [
        holdout[run_key(mode, BASE_SLIPPAGE, protected=True)]
        for mode in (TimingMode.IMMEDIATE, TimingMode.HOLD_30S)
    ]
    candidate = max(candidates, key=lambda result: result.return_pct)
    if candidate.return_pct <= completed.return_pct:
        return TimingMode.COMPLETED.value, "holdout return did not beat completed mode"
    if candidate.max_drawdown_pct > completed.max_drawdown_pct + Decimal("2"):
        return TimingMode.COMPLETED.value, "holdout MDD was more than 2 percentage points higher"

    stressed_candidate = holdout[
        run_key(candidate.mode, STRESS_SLIPPAGE, protected=True)
    ]
    stressed_completed = holdout[
        run_key(TimingMode.COMPLETED, STRESS_SLIPPAGE, protected=True)
    ]
    if stressed_candidate.return_pct <= stressed_completed.return_pct:
        return TimingMode.COMPLETED.value, "advantage did not survive 0.30% slippage"
    return candidate.mode.value, "holdout return, MDD, and 0.30% slippage criteria passed"

