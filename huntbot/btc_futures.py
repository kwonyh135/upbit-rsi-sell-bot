from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum

from huntbot.models import Candle


FIVE_MINUTES = timedelta(minutes=5)
FOUR_HOURS = timedelta(hours=4)
FOUR_HOUR_CANDLE_COUNT = 48


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_candle(candle: Candle) -> Candle:
    timestamp = _as_utc(candle.timestamp)
    if candle.unit != 5:
        raise ValueError("expected five-minute candles")
    if candle.market != "BTCUSDT":
        raise ValueError("expected BTCUSDT candles")
    if timestamp.second or timestamp.microsecond or timestamp.minute % 5:
        raise ValueError("candle timestamps must align to five-minute boundaries")
    if timestamp == candle.timestamp:
        return candle
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
        if existing != candle:
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


__all__ = ["Regime", "classify_regimes", "validate_candles"]
