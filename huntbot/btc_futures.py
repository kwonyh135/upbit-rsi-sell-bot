from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum

from huntbot.bitget_public import FundingSettlement
from huntbot.indicators import rsi
from huntbot.models import Candle


FIVE_MINUTES = timedelta(minutes=5)
FOUR_HOURS = timedelta(hours=4)
FOUR_HOUR_CANDLE_COUNT = 48


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class StrategyKind(str, Enum):
    CASH = "cash"
    BUY_AND_HOLD = "buy_and_hold"
    LONG_ONLY = "long_only"
    SHORT_ONLY = "short_only"
    BIDIRECTIONAL = "bidirectional"
    REGIME_FILTERED = "regime_filtered"


@dataclass(frozen=True)
class FuturesConfig:
    kind: StrategyKind
    initial_equity: Decimal = Decimal("3000")
    fee_rate: Decimal = Decimal("0.0006")
    slippage: Decimal = Decimal("0.0002")
    rsi_period: int = 14
    thresholds: object | None = None


@dataclass(frozen=True)
class FuturesTrade:
    timestamp: datetime
    action: str
    market_price: Decimal
    execution_price: Decimal
    quantity: Decimal
    target_exposure: Decimal
    fee: Decimal
    slippage_cost: Decimal
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: Decimal
    exposure: Decimal
    regime: Regime


@dataclass(frozen=True)
class PositionCycle:
    direction: str
    opened_at: datetime
    closed_at: datetime
    pnl: Decimal


@dataclass(frozen=True)
class FuturesResult:
    config: FuturesConfig
    starting_equity: Decimal
    ending_equity: Decimal
    return_pct: Decimal
    annualized_return_pct: Decimal
    max_drawdown_pct: Decimal
    gross_pnl: Decimal
    fee_cost: Decimal
    slippage_cost: Decimal
    funding_pnl: Decimal
    turnover: Decimal
    time_in_market_pct: Decimal
    win_rate_pct: Decimal
    profit_factor: Decimal
    average_win: Decimal
    average_loss: Decimal
    long_pnl: Decimal
    short_pnl: Decimal
    trades: tuple[FuturesTrade, ...]
    cycles: tuple[PositionCycle, ...]
    equity_curve: tuple[EquityPoint, ...]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_candle(candle: Candle) -> Candle:
    if candle.unit != 5:
        raise ValueError("expected five-minute candles")
    if candle.market != "BTCUSDT":
        raise ValueError("expected BTCUSDT candles")
    timestamp = _as_utc(candle.timestamp)
    if timestamp.second or timestamp.microsecond or timestamp.minute % 5:
        raise ValueError("candle timestamps must align to five-minute boundaries")
    return Candle(
        market=candle.market,
        unit=candle.unit,
        timestamp=timestamp,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )


def _missing_intervals_between(previous: datetime, current: datetime) -> int:
    gap = current - previous
    steps = int(gap.total_seconds() // FIVE_MINUTES.total_seconds())
    return max(0, steps - 1)


def _count_missing_intervals(candles: list[Candle]) -> int:
    return sum(
        _missing_intervals_between(previous.timestamp, current.timestamp)
        for previous, current in zip(candles, candles[1:])
    )


def _count_missing_required(candles: list[Candle], *, start: datetime, end: datetime) -> int:
    if start.second or start.microsecond or start.minute % 5:
        raise ValueError("start must align to five-minute boundaries")
    if end.second or end.microsecond or end.minute % 5:
        raise ValueError("end must align to five-minute boundaries")
    required_steps = int((end - start).total_seconds() // FIVE_MINUTES.total_seconds())
    timestamps = {item.timestamp for item in candles if start <= item.timestamp < end}
    missing = 0
    for step in range(required_steps):
        timestamp = start + (step * FIVE_MINUTES)
        if timestamp not in timestamps:
            missing += 1
    return missing


def validate_candles(candles: list[Candle], start: datetime, end: datetime) -> tuple[list[Candle], int]:
    start = _as_utc(start)
    end = _as_utc(end)
    if end <= start:
        raise ValueError("end must be after start")

    ordered = sorted((_normalize_candle(candle) for candle in candles), key=lambda item: item.timestamp)
    unique: dict[datetime, Candle] = {}
    for candle in ordered:
        existing = unique.get(candle.timestamp)
        if existing is None:
            unique[candle.timestamp] = candle
            continue
        if (
            existing.open != candle.open
            or existing.high != candle.high
            or existing.low != candle.low
            or existing.close != candle.close
        ):
            raise ValueError(f"conflicting duplicate candle at {candle.timestamp.isoformat()}")

    validated = [unique[key] for key in sorted(unique)]
    missing_intervals = _count_missing_intervals(validated)
    missing_required = _count_missing_required(validated, start=start, end=end)
    if missing_required:
        interval_label = "interval" if missing_required == 1 else "intervals"
        raise ValueError(f"missing {missing_required} required five-minute {interval_label} in test window")
    return validated, missing_intervals


def _four_hour_bucket_start(timestamp: datetime) -> datetime:
    return timestamp.replace(minute=0, second=0, microsecond=0, hour=timestamp.hour - (timestamp.hour % 4))


def _is_complete_bucket(candles: list[Candle]) -> bool:
    if len(candles) != FOUR_HOUR_CANDLE_COUNT:
        return False
    start = _four_hour_bucket_start(candles[0].timestamp)
    for index, candle in enumerate(candles):
        if candle.timestamp != start + (index * FIVE_MINUTES):
            return False
    return True


def _ema(previous: Decimal | None, close: Decimal, period: int) -> Decimal:
    if previous is None:
        return close
    alpha = Decimal(2) / Decimal(period + 1)
    return previous + ((close - previous) * alpha)


def _label(close: Decimal, ema50: Decimal, ema200: Decimal) -> Regime:
    if close > ema200 and ema50 > ema200:
        return Regime.BULL
    if close < ema200 and ema50 < ema200:
        return Regime.BEAR
    return Regime.NEUTRAL


def classify_regimes(candles: list[Candle]) -> dict[datetime, Regime]:
    ordered = sorted((_normalize_candle(candle) for candle in candles), key=lambda item: item.timestamp)
    regimes: dict[datetime, Regime] = {}
    current_regime = Regime.NEUTRAL
    ema50: Decimal | None = None
    ema200: Decimal | None = None
    bucket_start: datetime | None = None
    bucket: list[Candle] = []

    for candle in ordered:
        current_bucket_start = _four_hour_bucket_start(candle.timestamp)
        if bucket_start is None:
            bucket_start = current_bucket_start
        elif current_bucket_start != bucket_start:
            if _is_complete_bucket(bucket):
                close = bucket[-1].close
                ema50 = _ema(ema50, close, 50)
                ema200 = _ema(ema200, close, 200)
                current_regime = _label(close, ema50, ema200)
            bucket_start = current_bucket_start
            bucket = []

        regimes[candle.timestamp] = current_regime
        bucket.append(candle)

    return regimes


def _threshold_value(thresholds: object | None, name: str, default: float | None) -> float | None:
    if thresholds is None:
        return default
    return getattr(thresholds, name)


def desired_target(
    kind: StrategyKind,
    exposure: Decimal,
    rsi_value: float,
    regime: Regime,
    thresholds: object | None = None,
) -> Decimal:
    if kind == StrategyKind.CASH:
        return Decimal("0")
    if kind == StrategyKind.BUY_AND_HOLD:
        return Decimal("1")
    long_entry_1 = _threshold_value(thresholds, "long_entry_1", 45)
    long_entry_2 = _threshold_value(thresholds, "long_entry_2", 40)
    long_exit_1 = _threshold_value(thresholds, "long_exit_1", 60)
    long_exit_2 = _threshold_value(thresholds, "long_exit_2", 65)
    short_entry_1 = _threshold_value(thresholds, "short_entry_1", 60)
    short_entry_2 = _threshold_value(thresholds, "short_entry_2", 65)
    short_exit_1 = _threshold_value(thresholds, "short_exit_1", 45)
    short_exit_2 = _threshold_value(thresholds, "short_exit_2", 40)
    allow_long = kind in {StrategyKind.LONG_ONLY, StrategyKind.BIDIRECTIONAL}
    allow_short = kind in {StrategyKind.SHORT_ONLY, StrategyKind.BIDIRECTIONAL}
    if kind == StrategyKind.REGIME_FILTERED:
        allow_long = regime == Regime.BULL
        allow_short = regime == Regime.BEAR
    if exposure > 0:
        if long_exit_2 is not None and rsi_value >= long_exit_2:
            return Decimal("0")
        if long_exit_1 is not None and rsi_value >= long_exit_1:
            return min(exposure, Decimal("0.5"))
        if long_entry_2 is not None and rsi_value <= long_entry_2:
            return Decimal("1")
        return exposure
    if exposure < 0:
        if short_exit_2 is not None and rsi_value <= short_exit_2:
            return Decimal("0")
        if short_exit_1 is not None and rsi_value <= short_exit_1:
            return max(exposure, Decimal("-0.5"))
        if short_entry_2 is not None and rsi_value >= short_entry_2:
            return Decimal("-1")
        return exposure
    if long_entry_1 is not None and rsi_value <= long_entry_1 and allow_long:
        return Decimal("0.5")
    if short_entry_1 is not None and rsi_value >= short_entry_1 and allow_short:
        return Decimal("-0.5")
    return Decimal("0")


def _guard_reversal(exposure: Decimal, target: Decimal) -> Decimal:
    if exposure and target and (exposure > 0) != (target > 0):
        return Decimal("0")
    return target


def _execution_price(price: Decimal, quantity_delta: Decimal, slippage: Decimal) -> Decimal:
    return price * (Decimal("1") + slippage if quantity_delta > 0 else Decimal("1") - slippage)


def _exposure(quantity: Decimal, price: Decimal, equity: Decimal) -> Decimal:
    if not quantity or equity <= 0:
        return Decimal("0")
    value = quantity * price / equity
    return max(Decimal("-1"), min(Decimal("1"), value))


def run_futures_backtest(
    candles: list[Candle],
    funding: list[FundingSettlement],
    regimes: dict[datetime, Regime],
    config: FuturesConfig,
    *,
    rsi_values: dict[datetime, float] | None = None,
) -> FuturesResult:
    ordered = sorted((_normalize_candle(item) for item in candles), key=lambda item: item.timestamp)
    if len(ordered) < 2:
        raise ValueError("at least two candles are required")
    if rsi_values is None:
        calculated = rsi([float(item.close) for item in ordered], period=config.rsi_period)
        rsi_values = {item.timestamp: value for item, value in zip(ordered, calculated) if value is not None}
    else:
        rsi_values = {_as_utc(key): value for key, value in rsi_values.items()}
    funding_by_time: dict[datetime, list[Decimal]] = {}
    for item in funding:
        funding_by_time.setdefault(_as_utc(item.timestamp), []).append(item.rate)

    cash = config.initial_equity
    quantity = Decimal("0")
    trades: list[FuturesTrade] = []
    cycles: list[PositionCycle] = []
    curve: list[EquityPoint] = []
    fee_cost = slippage_cost = funding_pnl = turnover = Decimal("0")
    pending_target: Decimal | None = None
    target_exposure = Decimal("0")
    cycle_opened: datetime | None = None
    cycle_start_equity = config.initial_equity
    cycle_direction = ""
    long_pnl = short_pnl = Decimal("0")

    for index, candle in enumerate(ordered):
        market_price = candle.open
        for rate in funding_by_time.get(candle.timestamp, []):
            payment = -(quantity * market_price * rate)
            cash += payment
            funding_pnl += payment
        equity_before = cash + quantity * market_price
        current_exposure = _exposure(quantity, market_price, equity_before)
        if pending_target is not None:
            target = _guard_reversal(current_exposure, pending_target)
            target_notional = target * equity_before
            provisional_delta = (target_notional / market_price) - quantity
            if provisional_delta:
                execution_price = _execution_price(market_price, provisional_delta, config.slippage)
                target_quantity = target_notional / execution_price
                delta = target_quantity - quantity
                notional = abs(delta * execution_price)
                fee = notional * config.fee_rate
                slip = abs(execution_price - market_price) * abs(delta)
                cash -= delta * execution_price + fee
                quantity += delta
                fee_cost += fee
                slippage_cost += slip
                turnover += notional
                action = "buy" if delta > 0 else "sell"
                trades.append(FuturesTrade(candle.timestamp, action, market_price, execution_price, delta, target, fee, slip, "signal"))
                if current_exposure == 0 and target != 0:
                    cycle_opened = candle.timestamp
                    cycle_start_equity = equity_before
                    cycle_direction = "long" if target > 0 else "short"
                elif current_exposure != 0 and target == 0 and cycle_opened is not None:
                    closed_equity = cash
                    pnl = closed_equity - cycle_start_equity
                    cycles.append(PositionCycle(cycle_direction, cycle_opened, candle.timestamp, pnl))
                    if cycle_direction == "long":
                        long_pnl += pnl
                    else:
                        short_pnl += pnl
                    cycle_opened = None
            target_exposure = target
            pending_target = None

        close_equity = cash + quantity * candle.close
        regime = regimes.get(candle.timestamp, Regime.NEUTRAL)
        curve.append(EquityPoint(candle.timestamp, close_equity, _exposure(quantity, candle.close, close_equity), regime))
        value = rsi_values.get(candle.timestamp)
        if config.kind == StrategyKind.BUY_AND_HOLD and index == 0 and index + 1 < len(ordered):
            pending_target = Decimal("1")
        elif value is not None and index + 1 < len(ordered):
            desired = desired_target(config.kind, target_exposure, value, regime, config.thresholds)
            if desired != target_exposure:
                pending_target = desired

    if quantity:
        final = ordered[-1]
        market_price = final.close
        delta = -quantity
        execution_price = _execution_price(market_price, delta, config.slippage)
        notional = abs(delta * execution_price)
        fee = notional * config.fee_rate
        slip = abs(execution_price - market_price) * abs(delta)
        cash -= delta * execution_price + fee
        fee_cost += fee
        slippage_cost += slip
        turnover += notional
        trades.append(FuturesTrade(final.timestamp, "sell" if delta < 0 else "buy", market_price, execution_price, delta, Decimal("0"), fee, slip, "end_of_test"))
        if cycle_opened is not None:
            pnl = cash - cycle_start_equity
            cycles.append(PositionCycle(cycle_direction, cycle_opened, final.timestamp, pnl))
            if cycle_direction == "long": long_pnl += pnl
            else: short_pnl += pnl
        curve[-1] = EquityPoint(final.timestamp, cash, Decimal("0"), regimes.get(final.timestamp, Regime.NEUTRAL))

    ending = cash
    gross_pnl = ending - config.initial_equity + fee_cost + slippage_cost - funding_pnl
    return_pct = (ending / config.initial_equity - Decimal("1")) * Decimal("100")
    elapsed_days = Decimal(str((ordered[-1].timestamp - ordered[0].timestamp).total_seconds())) / Decimal("86400")
    annualized = return_pct * Decimal("365") / elapsed_days if elapsed_days > 0 else Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    occupied = 0
    for point in curve:
        peak = max(peak, point.equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - point.equity) / peak * Decimal("100"))
        occupied += int(point.exposure != 0)
    wins = [item.pnl for item in cycles if item.pnl > 0]
    losses = [item.pnl for item in cycles if item.pnl < 0]
    profit_factor = sum(wins, Decimal("0")) / abs(sum(losses, Decimal("0"))) if losses else (Decimal("999") if wins else Decimal("0"))
    return FuturesResult(
        config, config.initial_equity, ending, return_pct, annualized, max_dd,
        gross_pnl, fee_cost, slippage_cost, funding_pnl, turnover,
        Decimal(occupied) / Decimal(len(curve)) * Decimal("100"),
        Decimal(len(wins)) / Decimal(len(cycles)) * Decimal("100") if cycles else Decimal("0"),
        profit_factor,
        sum(wins, Decimal("0")) / Decimal(len(wins)) if wins else Decimal("0"),
        sum(losses, Decimal("0")) / Decimal(len(losses)) if losses else Decimal("0"),
        long_pnl, short_pnl, tuple(trades), tuple(cycles), tuple(curve),
    )


__all__ = [
    "EquityPoint", "FuturesConfig", "FuturesResult", "FuturesTrade", "PositionCycle",
    "Regime", "StrategyKind", "classify_regimes", "desired_target", "run_futures_backtest",
    "validate_candles",
]
