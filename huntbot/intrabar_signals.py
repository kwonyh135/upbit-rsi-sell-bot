from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Sequence

from huntbot.indicators import rsi
from huntbot.second_data import SecondCandle


@dataclass(frozen=True)
class FiveMinuteBar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class TimingMode(str, Enum):
    COMPLETED = "completed"
    IMMEDIATE = "immediate"
    HOLD_30S = "hold_30s"


@dataclass(frozen=True)
class TimedSignal:
    action: str
    timestamp: datetime
    candle_start: datetime
    rsi_value: float


@dataclass(frozen=True)
class SignalTracker:
    active_action: str | None = None
    active_since: datetime | None = None
    active_candle: datetime | None = None
    active_rsi_value: float | None = None
    acted_candle: datetime | None = None


def five_minute_bucket(timestamp: datetime) -> datetime:
    return timestamp.replace(
        minute=timestamp.minute - (timestamp.minute % 5),
        second=0,
        microsecond=0,
    )


def aggregate_five_minute_bars(seconds: Sequence[SecondCandle]) -> list[FiveMinuteBar]:
    bars: list[FiveMinuteBar] = []
    current_bucket: datetime | None = None
    current_bar: FiveMinuteBar | None = None

    for item in sorted(seconds, key=lambda candle: candle.timestamp):
        bucket = five_minute_bucket(item.timestamp)
        if bucket != current_bucket:
            if current_bar is not None:
                bars.append(current_bar)
            current_bucket = bucket
            current_bar = FiveMinuteBar(
                timestamp=bucket,
                open=item.open,
                high=item.high,
                low=item.low,
                close=item.close,
                volume=item.volume,
            )
            continue
        assert current_bar is not None
        current_bar = FiveMinuteBar(
            timestamp=current_bar.timestamp,
            open=current_bar.open,
            high=max(current_bar.high, item.high),
            low=min(current_bar.low, item.low),
            close=item.close,
            volume=current_bar.volume + item.volume,
        )

    if current_bar is not None:
        bars.append(current_bar)
    return bars


def provisional_rsi(
    completed_closes: Sequence[Decimal],
    current_price: Decimal,
    *,
    period: int = 14,
) -> float | None:
    if len(completed_closes) < period:
        return None
    return rsi([float(value) for value in [*completed_closes, current_price]], period=period)[-1]


def threshold_action(
    phase: str,
    rsi_value: float | None,
    *,
    has_hunt: bool,
    has_krw: bool,
) -> str | None:
    if rsi_value is None:
        return None
    if rsi_value >= 65 and has_hunt:
        return "sell_2"
    if rsi_value >= 60 and has_hunt and phase != "sell_2":
        return "sell_1"
    if phase == "buy_2":
        return "buy_2" if rsi_value <= 40 and has_krw else None
    return "buy_1" if rsi_value <= 45 and has_krw else None


def observe_signal(
    *,
    mode: TimingMode,
    timestamp: datetime,
    candle_start: datetime,
    rsi_value: float | None,
    phase: str,
    has_hunt: bool,
    has_krw: bool,
    tracker: SignalTracker,
) -> tuple[TimedSignal | None, SignalTracker]:
    action = threshold_action(phase, rsi_value, has_hunt=has_hunt, has_krw=has_krw)

    if tracker.acted_candle == candle_start and action is not None:
        return None, _clear_active(tracker)

    if mode in {TimingMode.COMPLETED, TimingMode.IMMEDIATE}:
        if action is None:
            return None, _clear_active(tracker)
        return _emit_signal(
            action=action,
            timestamp=timestamp,
            candle_start=candle_start,
            rsi_value=rsi_value,
            tracker=tracker,
        )

    if action is None:
        return None, _clear_active(tracker)

    if tracker.active_action == action and tracker.active_candle == candle_start:
        return None, tracker

    next_tracker = SignalTracker(
        active_action=action,
        active_since=timestamp,
        active_candle=candle_start,
        active_rsi_value=rsi_value,
        acted_candle=tracker.acted_candle,
    )
    return None, next_tracker


def mature_held_signal(
    tracker: SignalTracker,
    timestamp: datetime,
) -> tuple[TimedSignal | None, SignalTracker]:
    if (
        tracker.active_action is None
        or tracker.active_since is None
        or tracker.active_candle is None
        or tracker.active_rsi_value is None
    ):
        return None, tracker
    if timestamp < tracker.active_since + timedelta(seconds=30):
        return None, tracker
    signal = TimedSignal(
        action=tracker.active_action,
        timestamp=tracker.active_since + timedelta(seconds=30),
        candle_start=tracker.active_candle,
        rsi_value=tracker.active_rsi_value,
    )
    return signal, SignalTracker(acted_candle=tracker.active_candle)


def _emit_signal(
    *,
    action: str,
    timestamp: datetime,
    candle_start: datetime,
    rsi_value: float | None,
    tracker: SignalTracker,
) -> tuple[TimedSignal, SignalTracker]:
    assert rsi_value is not None
    signal = TimedSignal(
        action=action,
        timestamp=timestamp,
        candle_start=candle_start,
        rsi_value=rsi_value,
    )
    return signal, SignalTracker(acted_candle=candle_start)


def _clear_active(tracker: SignalTracker) -> SignalTracker:
    if (
        tracker.active_action is None
        and tracker.active_since is None
        and tracker.active_candle is None
        and tracker.active_rsi_value is None
    ):
        return tracker
    return SignalTracker(acted_candle=tracker.acted_candle)
