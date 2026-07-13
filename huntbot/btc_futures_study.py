from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal

from huntbot.bitget_public import FundingSettlement
from huntbot.btc_futures import (
    FuturesConfig,
    FuturesResult,
    Regime,
    StrategyKind,
    classify_regimes,
    run_futures_backtest,
)
from huntbot.models import Candle


SLIPPAGES = (Decimal("0.0002"), Decimal("0.0005"), Decimal("0.001"))
KINDS = tuple(StrategyKind)


@dataclass(frozen=True)
class StudyRun:
    segment: str
    result: FuturesResult
    regime_contribution: dict[str, Decimal]


@dataclass(frozen=True)
class BtcFuturesStudy:
    start: datetime
    end: datetime
    holdout_start: datetime
    full_runs: tuple[StudyRun, ...]
    development_runs: tuple[StudyRun, ...]
    holdout_runs: tuple[StudyRun, ...]
    selected_strategy: str
    conclusion: str
    conclusion_reasons: tuple[str, ...]


def _shift_months(value: datetime, months: int) -> datetime:
    index = value.year * 12 + value.month - 1 + months
    return value.replace(year=index // 12, month=index % 12 + 1, day=1)


def _contribution(result: FuturesResult) -> dict[str, Decimal]:
    totals = {item.value: Decimal("0") for item in Regime}
    for previous, current in zip(result.equity_curve, result.equity_curve[1:]):
        totals[previous.regime.value] += current.equity - previous.equity
    return totals


def _run_segment(
    name: str,
    candles: list[Candle],
    funding: list[FundingSettlement],
    regimes: dict[datetime, Regime],
) -> tuple[StudyRun, ...]:
    if len(candles) < 2:
        raise ValueError(f"{name} segment requires at least two candles")
    runs = []
    for kind in KINDS:
        for slippage in SLIPPAGES:
            config = FuturesConfig(kind=kind, slippage=slippage)
            result = run_futures_backtest(candles, funding, regimes, config)
            runs.append(StudyRun(name, result, _contribution(result)))
    return tuple(runs)


def _primary(runs: tuple[StudyRun, ...], kind: StrategyKind, slippage: Decimal) -> FuturesResult:
    return next(run.result for run in runs if run.result.config.kind == kind and run.result.config.slippage == slippage)


def _profit_concentration(result: FuturesResult) -> Decimal:
    positive = [item.pnl for item in result.cycles if item.pnl > 0]
    if not positive:
        return Decimal("0")
    return max(positive) / sum(positive, Decimal("0")) * Decimal("100")


def classify_conclusion(
    *, holdout_return: Decimal, holdout_mdd: Decimal, stress_return: Decimal,
    cycles: int, profit_concentration: Decimal, buy_hold_return: Decimal, buy_hold_mdd: Decimal,
) -> tuple[str, tuple[str, ...]]:
    if holdout_return < 0:
        return "not recommended", ("negative holdout return after base costs",)
    reasons = []
    if holdout_mdd > Decimal("20"): reasons.append("holdout maximum drawdown exceeded 20%")
    if stress_return < 0: reasons.append("negative return under 0.05% slippage stress")
    if cycles < 10: reasons.append("fewer than ten completed holdout cycles")
    if profit_concentration > Decimal("50"): reasons.append("one cycle produced more than half of positive profit")
    if holdout_return < buy_hold_return and holdout_mdd >= buy_hold_mdd:
        reasons.append("underperformed buy-and-hold with comparable or greater drawdown")
    if reasons:
        return "inconclusive", tuple(reasons)
    return "recommended for further paper trading", ()


def run_btc_futures_study(
    candles: list[Candle],
    funding: list[FundingSettlement],
    start: datetime,
    end: datetime,
    *,
    holdout_start: datetime | None = None,
    allow_sparse: bool = False,
) -> BtcFuturesStudy:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    holdout_start = holdout_start or _shift_months(start, 4)
    ordered = sorted(
        (item for item in candles if start <= item.timestamp.astimezone(timezone.utc) < end),
        key=lambda item: item.timestamp,
    )
    if not allow_sparse:
        expected = int((end - start).total_seconds() // 300)
        if len({item.timestamp for item in ordered}) != expected:
            raise ValueError("study requires complete five-minute test coverage")
    development = [item for item in ordered if item.timestamp < holdout_start]
    holdout = [item for item in ordered if item.timestamp >= holdout_start]
    regimes = classify_regimes(candles)
    full_runs = _run_segment("full", ordered, funding, regimes)
    development_runs = _run_segment("development", development, funding, regimes)
    holdout_runs = _run_segment("holdout", holdout, funding, regimes)
    candidates = [kind for kind in KINDS if kind not in {StrategyKind.CASH, StrategyKind.BUY_AND_HOLD}]
    selected = max(candidates, key=lambda kind: _primary(holdout_runs, kind, SLIPPAGES[0]).return_pct)
    base = _primary(holdout_runs, selected, SLIPPAGES[0])
    stress = _primary(holdout_runs, selected, SLIPPAGES[1])
    benchmark = _primary(holdout_runs, StrategyKind.BUY_AND_HOLD, SLIPPAGES[0])
    conclusion, reasons = classify_conclusion(
        holdout_return=base.return_pct,
        holdout_mdd=base.max_drawdown_pct,
        stress_return=stress.return_pct,
        cycles=len(base.cycles),
        profit_concentration=_profit_concentration(base),
        buy_hold_return=benchmark.return_pct,
        buy_hold_mdd=benchmark.max_drawdown_pct,
    )
    return BtcFuturesStudy(start, end, holdout_start, full_runs, development_runs, holdout_runs, selected.value, conclusion, reasons)


def study_to_json(study: BtcFuturesStudy, metadata: dict) -> str:
    return json.dumps({"metadata": metadata, "study": asdict(study)}, ensure_ascii=True, indent=2, default=_json_default) + "\n"


def _json_default(value):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, StrategyKind): return value.value
    if isinstance(value, Regime): return value.value
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


__all__ = ["BtcFuturesStudy", "StudyRun", "classify_conclusion", "run_btc_futures_study", "study_to_json"]
