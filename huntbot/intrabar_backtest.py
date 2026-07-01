from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence

from huntbot.crash_backtest import ProtectionConfig, evaluate_protection
from huntbot.indicators import WilderRsiPreview
from huntbot.intrabar_signals import (
    FiveMinuteBar,
    SignalTracker,
    TimedSignal,
    TimingMode,
    five_minute_bucket,
    mature_held_signal,
    observe_signal,
)
from huntbot.second_data import SecondCandle


@dataclass(frozen=True)
class TimingBacktestConfig:
    mode: TimingMode
    fee_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    initial_krw: Decimal = Decimal("3000000")
    protection: ProtectionConfig | None = None


@dataclass(frozen=True)
class TimingTrade:
    action: str
    signal_timestamp: datetime
    signal_candle_start: datetime
    timestamp: datetime
    signal_price: Decimal
    market_price: Decimal
    execution_price: Decimal
    rsi_value: float
    quantity: Decimal
    cash: Decimal
    remaining_quantity: Decimal
    phase: str


@dataclass(frozen=True)
class TimingCycle:
    start_timestamp: datetime
    end_timestamp: datetime
    start_value: Decimal
    end_value: Decimal
    pnl: Decimal
    return_pct: Decimal


@dataclass(frozen=True)
class TimingBacktestResult:
    mode: TimingMode
    final_value: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    false_intrabar_signals: int
    emergency_exits: int
    final_cash: Decimal
    final_quantity: Decimal
    final_phase: str
    trades: tuple[TimingTrade, ...]
    cycles: tuple[TimingCycle, ...] = ()


@dataclass(frozen=True)
class PortfolioState:
    cash: Decimal
    quantity: Decimal
    average_price: Decimal
    phase: str


@dataclass(frozen=True)
class PendingSignal:
    signal: TimedSignal
    signal_price: Decimal


def execution_price(price: Decimal, action: str, slippage: Decimal) -> Decimal:
    if action.startswith("sell") or action == "emergency_sell":
        return price * (Decimal("1") - slippage)
    return price * (Decimal("1") + slippage)


def run_timing_backtest(
    seconds: Sequence[SecondCandle],
    config: TimingBacktestConfig,
) -> TimingBacktestResult:
    ordered = sorted(seconds, key=lambda item: item.timestamp)
    if not ordered:
        raise ValueError("at least one second candle is required")

    state = PortfolioState(config.initial_krw, Decimal("0"), Decimal("0"), "sell_1")
    tracker = SignalTracker()
    pending: PendingSignal | None = None
    trades: list[TimingTrade] = []
    cycles: list[TimingCycle] = []
    cycle_start: tuple[datetime, Decimal] | None = None
    rsi_preview = WilderRsiPreview()
    completed_bars: list[FiveMinuteBar] = []
    current_bar: FiveMinuteBar | None = None
    hold_signal_price: Decimal | None = None
    false_intrabar_signals = 0
    risk_streak = 0
    equity_points = [config.initial_krw]

    def fill_pending(tick: SecondCandle, *, allow_equal: bool = False) -> None:
        nonlocal state, pending, cycle_start
        if pending is None:
            return
        is_fillable = (
            tick.timestamp >= pending.signal.timestamp
            if allow_equal
            else tick.timestamp > pending.signal.timestamp
        )
        if not is_fillable:
            return
        previous_state = state
        state, trade = _fill_signal(state, pending, tick, config)
        trades.append(trade)
        if previous_state.quantity == 0 and state.quantity > 0:
            cycle_start = (trade.timestamp, previous_state.cash)
        elif previous_state.quantity > 0 and state.quantity == 0 and cycle_start is not None:
            start_timestamp, start_value = cycle_start
            pnl = state.cash - start_value
            cycles.append(
                TimingCycle(
                    start_timestamp=start_timestamp,
                    end_timestamp=trade.timestamp,
                    start_value=start_value,
                    end_value=state.cash,
                    pnl=pnl,
                    return_pct=(pnl / start_value * Decimal("100") if start_value else Decimal("0")),
                )
            )
            cycle_start = None
        pending = None

    for tick in ordered:
        fill_pending(tick)

        bucket = five_minute_bucket(tick.timestamp)
        matured, tracker = mature_held_signal(tracker, tick.timestamp)
        if matured is not None and pending is None:
            pending = PendingSignal(matured, hold_signal_price or tick.close)
            hold_signal_price = None
            fill_pending(tick)

        if current_bar is None or current_bar.timestamp != bucket:
            boundary_signal_created = False
            if current_bar is not None:
                boundary = current_bar.timestamp + timedelta(minutes=5)
                completed_rsi = rsi_preview.preview(current_bar.close)
                if config.mode != TimingMode.COMPLETED:
                    false_intrabar_signals += sum(
                        1
                        for trade in trades
                        if trade.signal_candle_start == current_bar.timestamp
                        and trade.action != "emergency_sell"
                        and not _action_confirmed(trade.action, completed_rsi)
                    )
                risk_blocks_normal = False
                if config.protection is not None and state.quantity > 0:
                    window = [*completed_bars, current_bar][-config.protection.high_window_bars :]
                    risk = evaluate_protection(
                        config.protection,
                        rolling_high=max(item.high for item in window),
                        current_price=current_bar.close,
                        average_price=state.average_price,
                        atr_pct=Decimal("0"),
                    )
                    adjacent = (
                        bool(completed_bars)
                        and current_bar.timestamp - completed_bars[-1].timestamp
                        == timedelta(minutes=5)
                    )
                    if not adjacent:
                        risk_streak = 0
                    risk_streak = risk_streak + 1 if risk.final_risk else 0
                    risk_blocks_normal = risk.final_risk
                    if risk_streak >= config.protection.confirmations:
                        emergency = TimedSignal(
                            action="emergency_sell",
                            timestamp=boundary,
                            candle_start=current_bar.timestamp,
                            rsi_value=completed_rsi or 0.0,
                        )
                        pending = PendingSignal(emergency, current_bar.close)
                        boundary_signal_created = True
                        risk_streak = 0
                else:
                    risk_streak = 0

                if (
                    config.mode == TimingMode.COMPLETED
                    and pending is None
                    and not risk_blocks_normal
                ):
                    signal, tracker = observe_signal(
                        mode=config.mode,
                        timestamp=boundary,
                        candle_start=current_bar.timestamp,
                        rsi_value=completed_rsi,
                        phase=state.phase,
                        has_hunt=state.quantity > 0,
                        has_krw=state.cash > 0,
                        tracker=tracker,
                    )
                    if signal is not None:
                        pending = PendingSignal(signal, current_bar.close)
                        boundary_signal_created = True
                rsi_preview.append(current_bar.close)
                completed_bars.append(current_bar)
            current_bar = FiveMinuteBar(bucket, tick.open, tick.high, tick.low, tick.close, tick.volume)
            if boundary_signal_created:
                fill_pending(tick, allow_equal=True)
        else:
            current_bar = FiveMinuteBar(
                bucket,
                current_bar.open,
                max(current_bar.high, tick.high),
                min(current_bar.low, tick.low),
                tick.close,
                current_bar.volume + tick.volume,
            )

        if config.mode != TimingMode.COMPLETED:
            rsi_value = rsi_preview.preview(tick.close)
            previous_active_since = tracker.active_since
            signal, tracker = observe_signal(
                mode=config.mode,
                timestamp=tick.timestamp,
                candle_start=bucket,
                rsi_value=rsi_value,
                phase=state.phase,
                has_hunt=state.quantity > 0,
                has_krw=state.cash > 0,
                tracker=tracker,
            )
            if tracker.active_since is None:
                hold_signal_price = None
            elif tracker.active_since != previous_active_since:
                hold_signal_price = tick.close
            if signal is not None and pending is None:
                pending = PendingSignal(signal, tick.close)
        equity_points.append(state.cash + state.quantity * tick.close)

    final_value = state.cash + state.quantity * ordered[-1].close
    equity_points.append(final_value)
    peak = equity_points[0]
    max_drawdown = Decimal("0")
    for value in equity_points:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * Decimal("100"))
    return TimingBacktestResult(
        mode=config.mode,
        final_value=final_value,
        return_pct=(final_value - config.initial_krw) / config.initial_krw * Decimal("100"),
        max_drawdown_pct=max_drawdown,
        false_intrabar_signals=false_intrabar_signals,
        emergency_exits=sum(1 for trade in trades if trade.action == "emergency_sell"),
        final_cash=state.cash,
        final_quantity=state.quantity,
        final_phase=state.phase,
        trades=tuple(trades),
        cycles=tuple(cycles),
    )


def _fill_signal(
    state: PortfolioState,
    pending: PendingSignal,
    tick: SecondCandle,
    config: TimingBacktestConfig,
) -> tuple[PortfolioState, TimingTrade]:
    action = pending.signal.action
    if action not in {"buy_1", "buy_2", "sell_1", "sell_2", "emergency_sell"}:
        raise ValueError(f"unsupported action: {action}")
    price = execution_price(tick.close, action, config.slippage_rate)
    cash = state.cash
    quantity = state.quantity
    average_price = state.average_price

    if action in {"buy_1", "buy_2"}:
        spend = cash / Decimal("2") if action == "buy_1" else cash
        bought = spend / (Decimal("1") + config.fee_rate) / price
        total_quantity = quantity + bought
        average_price = (
            (quantity * average_price + spend) / total_quantity
            if total_quantity > 0
            else Decimal("0")
        )
        cash -= spend
        quantity = total_quantity
        traded_quantity = bought
        phase = "buy_2" if action == "buy_1" else "sell_1"
    elif action == "emergency_sell":
        sold = quantity
        cash += sold * price * (Decimal("1") - config.fee_rate)
        quantity = Decimal("0")
        average_price = Decimal("0")
        traded_quantity = sold
        phase = "sell_1"
    else:
        sold = quantity / Decimal("2") if action == "sell_1" else quantity
        cash += sold * price * (Decimal("1") - config.fee_rate)
        quantity -= sold
        traded_quantity = sold
        phase = "sell_2" if action == "sell_1" else "buy_1"
        if quantity == 0:
            average_price = Decimal("0")

    next_state = PortfolioState(cash, quantity, average_price, phase)
    trade = TimingTrade(
        action=action,
        signal_timestamp=pending.signal.timestamp,
        signal_candle_start=pending.signal.candle_start,
        timestamp=tick.timestamp,
        signal_price=pending.signal_price,
        market_price=tick.close,
        execution_price=price,
        rsi_value=pending.signal.rsi_value,
        quantity=traded_quantity,
        cash=cash,
        remaining_quantity=quantity,
        phase=phase,
    )
    return next_state, trade


def _action_confirmed(action: str, rsi_value: float | None) -> bool:
    if rsi_value is None:
        return False
    if action == "sell_1":
        return rsi_value >= 60
    if action == "sell_2":
        return rsi_value >= 65
    if action == "buy_1":
        return rsi_value <= 45
    if action == "buy_2":
        return rsi_value <= 40
    return True
