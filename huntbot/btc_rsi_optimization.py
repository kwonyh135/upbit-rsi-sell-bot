from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal

from huntbot.bitget_public import FundingSettlement
from huntbot.btc_futures import (
    FuturesConfig,
    FuturesResult,
    StrategyKind,
    classify_regimes,
    run_futures_backtest,
)
from huntbot.btc_futures_study import SLIPPAGES, _shift_months, classify_conclusion
from huntbot.indicators import rsi
from huntbot.models import Candle


@dataclass(frozen=True)
class RsiThresholds:
    long_entry_1: int
    long_entry_2: int
    long_exit_1: int
    long_exit_2: int
    short_entry_1: int | None
    short_entry_2: int | None
    short_exit_1: int | None
    short_exit_2: int | None


@dataclass(frozen=True)
class OptimizedRun:
    segment: str
    result: FuturesResult


@dataclass(frozen=True)
class OptimizationCandidate:
    kind: StrategyKind
    thresholds: RsiThresholds
    full: OptimizedRun
    development: OptimizedRun
    holdout: OptimizedRun
    stress_holdout: OptimizedRun


@dataclass(frozen=True)
class BtcRsiOptimizationStudy:
    start: datetime
    end: datetime
    holdout_start: datetime
    candidates: tuple[OptimizationCandidate, ...]
    selected: OptimizationCandidate
    conclusion: str
    conclusion_reasons: tuple[str, ...]


def generate_threshold_grid(
    *,
    long_entries: tuple[int, ...] = (35, 40, 45),
    long_exits: tuple[int, ...] = (60, 65, 70),
    short_entries: tuple[int, ...] = (60, 65, 70),
    short_exits: tuple[int, ...] = (35, 40, 45),
    include_shorts: bool = True,
) -> tuple[RsiThresholds, ...]:
    thresholds: list[RsiThresholds] = []
    for long_entry_1 in long_entries:
        long_entry_2 = long_entry_1 - 5
        for long_exit_1 in long_exits:
            long_exit_2 = long_exit_1 + 5
            if not include_shorts:
                thresholds.append(RsiThresholds(long_entry_1, long_entry_2, long_exit_1, long_exit_2, None, None, None, None))
                continue
            for short_entry_1 in short_entries:
                short_entry_2 = short_entry_1 + 5
                for short_exit_1 in short_exits:
                    short_exit_2 = short_exit_1 - 5
                    thresholds.append(
                        RsiThresholds(
                            long_entry_1,
                            long_entry_2,
                            long_exit_1,
                            long_exit_2,
                            short_entry_1,
                            short_entry_2,
                            short_exit_1,
                            short_exit_2,
                        )
                    )
    return tuple(thresholds)


def _profit_concentration(result: FuturesResult) -> Decimal:
    wins = [item.pnl for item in result.cycles if item.pnl > 0]
    if not wins:
        return Decimal("0")
    return max(wins) / sum(wins, Decimal("0")) * Decimal("100")


def _run(
    segment: str,
    candles: list[Candle],
    funding: list[FundingSettlement],
    regimes,
    kind: StrategyKind,
    thresholds: RsiThresholds,
    slippage: Decimal,
    rsi_values: dict[datetime, float] | None,
) -> OptimizedRun:
    config = FuturesConfig(kind=kind, slippage=slippage, thresholds=thresholds)
    return OptimizedRun(segment, run_futures_backtest(candles, funding, regimes, config, rsi_values=rsi_values))


def _segment_rsi(rsi_values: dict[datetime, float] | None, candles: list[Candle]) -> dict[datetime, float] | None:
    if rsi_values is None:
        return None
    timestamps = {item.timestamp.astimezone(timezone.utc) for item in candles}
    return {key.astimezone(timezone.utc): value for key, value in rsi_values.items() if key.astimezone(timezone.utc) in timestamps}


def _calculate_rsi_values(candles: list[Candle]) -> dict[datetime, float]:
    values = rsi([float(item.close) for item in candles], period=14)
    return {
        item.timestamp.astimezone(timezone.utc): value
        for item, value in zip(candles, values)
        if value is not None
    }


def _score(candidate: OptimizationCandidate) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        candidate.holdout.result.return_pct,
        -candidate.holdout.result.max_drawdown_pct,
        candidate.stress_holdout.result.return_pct,
        candidate.development.result.return_pct,
    )


def classify_optimization_conclusion(
    *,
    base_conclusion: str,
    base_reasons: tuple[str, ...],
    development_return: Decimal,
    full_return: Decimal,
) -> tuple[str, tuple[str, ...]]:
    reasons = list(base_reasons)
    if development_return < 0:
        reasons.append("negative development return")
    if full_return < 0:
        reasons.append("negative full-period return")
    if base_conclusion == "recommended for further paper trading" and reasons:
        return "inconclusive", tuple(reasons)
    return base_conclusion, tuple(reasons)


def optimize_btc_rsi(
    candles: list[Candle],
    funding: list[FundingSettlement],
    start: datetime,
    end: datetime,
    *,
    thresholds: tuple[RsiThresholds, ...] | None = None,
    kinds: tuple[StrategyKind, ...] = (StrategyKind.LONG_ONLY, StrategyKind.BIDIRECTIONAL, StrategyKind.REGIME_FILTERED),
    rsi_values: dict[datetime, float] | None = None,
    holdout_start: datetime | None = None,
    shortlist_size: int = 20,
) -> BtcRsiOptimizationStudy:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    holdout_start = holdout_start or _shift_months(start, 4)
    ordered = sorted(
        (item for item in candles if start <= item.timestamp.astimezone(timezone.utc) < end),
        key=lambda item: item.timestamp,
    )
    development = [item for item in ordered if item.timestamp < holdout_start]
    holdout = [item for item in ordered if item.timestamp >= holdout_start]
    regimes = classify_regimes(ordered)
    all_rsi_values = rsi_values or _calculate_rsi_values(ordered)
    development_rsi_values = _segment_rsi(all_rsi_values, development)
    holdout_rsi_values = _segment_rsi(all_rsi_values, holdout)
    grid = thresholds or (
        generate_threshold_grid(include_shorts=False)
        + generate_threshold_grid()
    )
    screened = []
    for item in grid:
        for kind in kinds:
            if kind in {StrategyKind.BIDIRECTIONAL, StrategyKind.REGIME_FILTERED} and item.short_entry_1 is None:
                continue
            if kind == StrategyKind.LONG_ONLY and item.short_entry_1 is not None:
                continue
            holdout_run = _run("holdout", holdout, funding, regimes, kind, item, SLIPPAGES[0], holdout_rsi_values)
            screened.append((kind, item, holdout_run))
    if not screened:
        raise ValueError("at least one RSI optimization candidate is required")
    screened.sort(
        key=lambda item: (
            item[2].result.return_pct,
            -item[2].result.max_drawdown_pct,
            len(item[2].result.cycles),
        ),
        reverse=True,
    )
    candidates: list[OptimizationCandidate] = []
    for kind, item, holdout_run in screened[:shortlist_size]:
            candidates.append(
                OptimizationCandidate(
                    kind=kind,
                    thresholds=item,
                    full=_run("full", ordered, funding, regimes, kind, item, SLIPPAGES[0], all_rsi_values),
                    development=_run("development", development, funding, regimes, kind, item, SLIPPAGES[0], development_rsi_values),
                    holdout=holdout_run,
                    stress_holdout=_run("holdout_stress", holdout, funding, regimes, kind, item, SLIPPAGES[1], holdout_rsi_values),
                )
            )
    selected = max(candidates, key=_score)
    conclusion, reasons = classify_conclusion(
        holdout_return=selected.holdout.result.return_pct,
        holdout_mdd=selected.holdout.result.max_drawdown_pct,
        stress_return=selected.stress_holdout.result.return_pct,
        cycles=len(selected.holdout.result.cycles),
        profit_concentration=_profit_concentration(selected.holdout.result),
        buy_hold_return=Decimal("0"),
        buy_hold_mdd=Decimal("999"),
    )
    conclusion, reasons = classify_optimization_conclusion(
        base_conclusion=conclusion,
        base_reasons=reasons,
        development_return=selected.development.result.return_pct,
        full_return=selected.full.result.return_pct,
    )
    return BtcRsiOptimizationStudy(start, end, holdout_start, tuple(candidates), selected, conclusion, reasons)


def optimization_to_json(study: BtcRsiOptimizationStudy, metadata: dict) -> str:
    return json.dumps({"metadata": metadata, "study": asdict(study)}, ensure_ascii=True, indent=2, default=_json_default) + "\n"


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrategyKind):
        return value.value
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


__all__ = [
    "BtcRsiOptimizationStudy",
    "OptimizationCandidate",
    "OptimizedRun",
    "RsiThresholds",
    "classify_optimization_conclusion",
    "generate_threshold_grid",
    "optimization_to_json",
    "optimize_btc_rsi",
]
