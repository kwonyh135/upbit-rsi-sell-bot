from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.bitget_public import FundingSettlement
from huntbot.models import Candle


FIVE_MINUTES = timedelta(minutes=5)
FOUR_HOURS = timedelta(hours=4)
FOUR_HOUR_CANDLE_COUNT = 48


@dataclass(frozen=True)
class TrendConfig:
    lookback: int
    initial_equity: Decimal = Decimal("3000")
    fee_rate: Decimal = Decimal("0.0006")
    slippage: Decimal = Decimal("0.0002")
    exposure: Decimal = Decimal("1")


@dataclass(frozen=True)
class TrendCycle:
    direction: str
    opened_at: datetime
    closed_at: datetime
    pnl: Decimal


@dataclass(frozen=True)
class TrendResult:
    config: TrendConfig
    start: datetime
    end: datetime
    ending_equity: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    fee_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal
    turnover: Decimal
    cycles: tuple[TrendCycle, ...]
    long_pnl: Decimal
    short_pnl: Decimal
    signals: int

    @property
    def win_rate_pct(self) -> Decimal:
        if not self.cycles:
            return Decimal("0")
        wins = sum(1 for item in self.cycles if item.pnl > 0)
        return Decimal(wins) / Decimal(len(self.cycles)) * Decimal("100")


@dataclass(frozen=True)
class CandidateScore:
    lookback: int
    train: TrendResult
    train_stress: TrendResult


@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    selected_lookback: int
    selected_train_return_pct: Decimal
    selected_train_stress_pct: Decimal
    test: TrendResult
    test_stress: TrendResult
    candidate_scores: tuple[CandidateScore, ...]


@dataclass(frozen=True)
class FixedLookbackSummary:
    lookback: int
    compounded_return_pct: Decimal
    stress_compounded_return_pct: Decimal
    worst_fold_return_pct: Decimal
    worst_fold_stress_pct: Decimal
    max_drawdown_pct: Decimal
    total_cycles: int
    positive_folds: int
    long_pnl: Decimal
    short_pnl: Decimal


@dataclass(frozen=True)
class WalkForwardStudy:
    start: datetime
    end: datetime
    train_months: int
    test_months: int
    lookbacks: tuple[int, ...]
    folds: tuple[WalkForwardFold, ...]
    selected_summary: FixedLookbackSummary
    fixed_summaries: tuple[FixedLookbackSummary, ...]
    conclusion: str
    conclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _FourHourBucket:
    timestamp: datetime
    high: Decimal
    low: Decimal
    close: Decimal


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _four_hour_start(timestamp: datetime) -> datetime:
    timestamp = _as_utc(timestamp)
    return timestamp.replace(minute=0, second=0, microsecond=0, hour=timestamp.hour - timestamp.hour % 4)


def _complete_four_hour_buckets(candles: list[Candle]) -> list[_FourHourBucket]:
    groups: dict[datetime, list[Candle]] = {}
    for candle in candles:
        groups.setdefault(_four_hour_start(candle.timestamp), []).append(candle)
    buckets = []
    for start in sorted(groups):
        bucket = sorted(groups[start], key=lambda item: item.timestamp)
        if len(bucket) != FOUR_HOUR_CANDLE_COUNT:
            continue
        if any(item.timestamp.astimezone(timezone.utc) != start + (index * FIVE_MINUTES) for index, item in enumerate(bucket)):
            continue
        buckets.append(
            _FourHourBucket(
                timestamp=start + FOUR_HOURS,
                high=max(item.high for item in bucket),
                low=min(item.low for item in bucket),
                close=bucket[-1].close,
            )
        )
    return buckets


def _donchian_signals(candles: list[Candle], lookback: int) -> dict[datetime, Decimal]:
    buckets = _complete_four_hour_buckets(candles)
    signals: dict[datetime, Decimal] = {}
    for index, bucket in enumerate(buckets):
        if index < lookback:
            continue
        previous = buckets[index - lookback:index]
        upper = max(item.high for item in previous)
        lower = min(item.low for item in previous)
        if bucket.close > upper:
            signals[bucket.timestamp] = Decimal("1")
        elif bucket.close < lower:
            signals[bucket.timestamp] = Decimal("-1")
    return signals


def donchian_signals(candles: list[Candle], lookback: int) -> dict[datetime, Decimal]:
    return _donchian_signals(candles, lookback)


def _execution_price(price: Decimal, quantity_delta: Decimal, slippage: Decimal) -> Decimal:
    return price * (Decimal("1") + slippage if quantity_delta > 0 else Decimal("1") - slippage)


def _exposure(quantity: Decimal, price: Decimal, equity: Decimal) -> Decimal:
    if not quantity or equity <= 0:
        return Decimal("0")
    return max(Decimal("-1"), min(Decimal("1"), quantity * price / equity))


def run_trend_backtest(
    candles: list[Candle],
    funding: list[FundingSettlement],
    start: datetime,
    end: datetime,
    config: TrendConfig,
) -> TrendResult:
    start = _as_utc(start)
    end = _as_utc(end)
    ordered_all = sorted((item for item in candles if _as_utc(item.timestamp) < end), key=lambda item: item.timestamp)
    ordered = [item for item in ordered_all if start <= _as_utc(item.timestamp) < end]
    if len(ordered) < 2:
        raise ValueError("trend backtest requires at least two test candles")
    signals = _donchian_signals(ordered_all, config.lookback)
    funding_by_time: dict[datetime, list[Decimal]] = {}
    for item in funding:
        funding_by_time.setdefault(_as_utc(item.timestamp), []).append(item.rate)

    cash = config.initial_equity
    quantity = Decimal("0")
    fee_cost = slippage_cost = funding_pnl = turnover = Decimal("0")
    peak = config.initial_equity
    max_drawdown = Decimal("0")
    cycles: list[TrendCycle] = []
    cycle_opened: datetime | None = None
    cycle_start_equity = config.initial_equity
    cycle_direction = ""
    long_pnl = short_pnl = Decimal("0")
    signal_count = 0

    def equity_at(price: Decimal) -> Decimal:
        return cash + quantity * price

    def set_target(target: Decimal, price: Decimal, timestamp: datetime) -> None:
        nonlocal cash, quantity, fee_cost, slippage_cost, turnover
        nonlocal cycle_opened, cycle_start_equity, cycle_direction, long_pnl, short_pnl
        equity_before = equity_at(price)
        target_quantity = Decimal("0") if target == 0 else (target * equity_before / price)
        delta = target_quantity - quantity
        if not delta:
            return
        execution_price = _execution_price(price, delta, config.slippage)
        target_quantity = Decimal("0") if target == 0 else (target * equity_before / execution_price)
        delta = target_quantity - quantity
        notional = abs(delta * execution_price)
        fee = notional * config.fee_rate
        slip = abs(execution_price - price) * abs(delta)
        cash -= delta * execution_price + fee
        quantity += delta
        fee_cost += fee
        slippage_cost += slip
        turnover += notional
        current_exposure = _exposure(quantity, price, equity_at(price))
        if target == 0 and cycle_opened is not None:
            pnl = equity_at(price) - cycle_start_equity
            cycles.append(TrendCycle(cycle_direction, cycle_opened, timestamp, pnl))
            if cycle_direction == "long":
                long_pnl += pnl
            else:
                short_pnl += pnl
            cycle_opened = None
            cycle_direction = ""
        elif target != 0 and cycle_opened is None and current_exposure != 0:
            cycle_opened = timestamp
            cycle_start_equity = equity_at(price)
            cycle_direction = "long" if target > 0 else "short"

    for candle in ordered:
        timestamp = _as_utc(candle.timestamp)
        market_price = candle.open
        for rate in funding_by_time.get(timestamp, []):
            payment = -(quantity * market_price * rate)
            cash += payment
            funding_pnl += payment
        target = signals.get(timestamp)
        if target is not None:
            target *= config.exposure
            current = _exposure(quantity, market_price, equity_at(market_price))
            if current and target and (current > 0) != (target > 0):
                set_target(Decimal("0"), market_price, timestamp)
            set_target(target, market_price, timestamp)
            signal_count += 1
        close_equity = equity_at(candle.close)
        peak = max(peak, close_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - close_equity) / peak * Decimal("100"))

    if quantity:
        final = ordered[-1]
        set_target(Decimal("0"), final.close, _as_utc(final.timestamp))
    ending = cash
    return_pct = (ending / config.initial_equity - Decimal("1")) * Decimal("100")
    return TrendResult(
        config=config,
        start=start,
        end=end,
        ending_equity=ending,
        return_pct=return_pct,
        max_drawdown_pct=max_drawdown,
        fee_cost=fee_cost,
        slippage_cost=slippage_cost,
        funding_pnl=funding_pnl,
        turnover=turnover,
        cycles=tuple(cycles),
        long_pnl=long_pnl,
        short_pnl=short_pnl,
        signals=signal_count,
    )


def _score(score: CandidateScore) -> tuple[Decimal, Decimal, Decimal, int]:
    return (
        score.train_stress.return_pct,
        -score.train_stress.max_drawdown_pct,
        score.train.return_pct,
        len(score.train.cycles),
    )


def _compound(returns: list[Decimal]) -> Decimal:
    multiplier = Decimal("1")
    for item in returns:
        multiplier *= Decimal("1") + item / Decimal("100")
    return (multiplier - Decimal("1")) * Decimal("100")


def _summary(lookback: int, results: list[TrendResult], stress_results: list[TrendResult]) -> FixedLookbackSummary:
    return FixedLookbackSummary(
        lookback=lookback,
        compounded_return_pct=_compound([item.return_pct for item in results]),
        stress_compounded_return_pct=_compound([item.return_pct for item in stress_results]),
        worst_fold_return_pct=min((item.return_pct for item in results), default=Decimal("0")),
        worst_fold_stress_pct=min((item.return_pct for item in stress_results), default=Decimal("0")),
        max_drawdown_pct=max((item.max_drawdown_pct for item in results), default=Decimal("0")),
        total_cycles=sum(len(item.cycles) for item in results),
        positive_folds=sum(1 for item in results if item.return_pct > 0),
        long_pnl=sum((item.long_pnl for item in results), Decimal("0")),
        short_pnl=sum((item.short_pnl for item in results), Decimal("0")),
    )


def _classify(summary: FixedLookbackSummary, folds: tuple[WalkForwardFold, ...]) -> tuple[str, tuple[str, ...]]:
    reasons = []
    if summary.stress_compounded_return_pct <= 0:
        reasons.append("out-of-sample compounded stress return is not positive")
    if summary.positive_folds < max(1, len(folds) // 2 + 1):
        reasons.append("fewer than half of out-of-sample folds are positive")
    if summary.max_drawdown_pct > Decimal("30"):
        reasons.append("one out-of-sample fold exceeded 30% maximum drawdown")
    selected = {fold.selected_lookback for fold in folds}
    if len(selected) > 4:
        reasons.append("selected lookback is unstable across folds")
    if reasons:
        return "research candidate, not live-ready", tuple(reasons)
    return "candidate for paper trading validation", ()


def run_walkforward_study(
    candles: list[Candle],
    funding: list[FundingSettlement],
    start: datetime,
    end: datetime,
    *,
    lookbacks: tuple[int, ...] = (20, 25, 30, 35, 40, 45, 50, 60, 80),
    train_months: int = 6,
    test_months: int = 3,
    base_slippage: Decimal = Decimal("0.0002"),
    stress_slippage: Decimal = Decimal("0.0005"),
) -> WalkForwardStudy:
    start = _as_utc(start)
    end = _as_utc(end)
    folds: list[WalkForwardFold] = []
    train_start = start
    index = 1
    while True:
        train_end = _shift_months(train_start, train_months)
        test_start = train_end
        test_end = _shift_months(test_start, test_months)
        if test_end > end:
            break
        scores = []
        for lookback in lookbacks:
            train = run_trend_backtest(candles, funding, train_start, train_end, TrendConfig(lookback=lookback, slippage=base_slippage))
            train_stress = run_trend_backtest(candles, funding, train_start, train_end, TrendConfig(lookback=lookback, slippage=stress_slippage))
            scores.append(CandidateScore(lookback, train, train_stress))
        selected = max(scores, key=_score)
        test = run_trend_backtest(candles, funding, test_start, test_end, TrendConfig(lookback=selected.lookback, slippage=base_slippage))
        test_stress = run_trend_backtest(candles, funding, test_start, test_end, TrendConfig(lookback=selected.lookback, slippage=stress_slippage))
        folds.append(
            WalkForwardFold(
                index=index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                selected_lookback=selected.lookback,
                selected_train_return_pct=selected.train.return_pct,
                selected_train_stress_pct=selected.train_stress.return_pct,
                test=test,
                test_stress=test_stress,
                candidate_scores=tuple(sorted(scores, key=_score, reverse=True)),
            )
        )
        train_start = _shift_months(train_start, test_months)
        index += 1

    selected_results = [fold.test for fold in folds]
    selected_stress = [fold.test_stress for fold in folds]
    selected_summary = _summary(0, selected_results, selected_stress)
    fixed_summaries = []
    for lookback in lookbacks:
        results = [
            run_trend_backtest(candles, funding, fold.test_start, fold.test_end, TrendConfig(lookback=lookback, slippage=base_slippage))
            for fold in folds
        ]
        stress_results = [
            run_trend_backtest(candles, funding, fold.test_start, fold.test_end, TrendConfig(lookback=lookback, slippage=stress_slippage))
            for fold in folds
        ]
        fixed_summaries.append(_summary(lookback, results, stress_results))
    conclusion, reasons = _classify(selected_summary, tuple(folds))
    return WalkForwardStudy(
        start=start,
        end=end,
        train_months=train_months,
        test_months=test_months,
        lookbacks=lookbacks,
        folds=tuple(folds),
        selected_summary=selected_summary,
        fixed_summaries=tuple(sorted(fixed_summaries, key=lambda item: item.stress_compounded_return_pct, reverse=True)),
        conclusion=conclusion,
        conclusion_reasons=reasons,
    )


def walkforward_to_json(study: WalkForwardStudy, metadata: dict) -> str:
    return json.dumps({"metadata": metadata, "study": asdict(study)}, ensure_ascii=True, indent=2, default=_json_default) + "\n"


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


__all__ = [
    "CandidateScore",
    "FixedLookbackSummary",
    "TrendConfig",
    "TrendCycle",
    "TrendResult",
    "WalkForwardFold",
    "WalkForwardStudy",
    "donchian_signals",
    "run_trend_backtest",
    "run_walkforward_study",
    "walkforward_to_json",
]
