from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from huntbot.indicators import rsi
from huntbot.models import Candle


@dataclass(frozen=True)
class ProtectionConfig:
    family: str
    name: str
    high_window_bars: int = 1
    high_drop_pct: Decimal = Decimal("0")
    average_loss_pct: Decimal = Decimal("0")
    confirmations: int = 1
    atr_floor_pct: Decimal = Decimal("0")
    atr_multiple: Decimal = Decimal("0")
    warning_drop_pct: Decimal = Decimal("0")
    warning_loss_pct: Decimal = Decimal("0")
    final_drop_pct: Decimal = Decimal("0")
    final_loss_pct: Decimal = Decimal("0")
    continuation_bars: int = 1


@dataclass(frozen=True)
class RecoveryConfig:
    mode: str
    name: str
    cooldown_bars: int = 0
    healthy_bars: int = 0


@dataclass(frozen=True)
class CrashEvent:
    action: str
    signal_timestamp: datetime
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    cash: Decimal
    remaining_quantity: Decimal
    phase: str


@dataclass(frozen=True)
class CrashBacktestResult:
    protection_name: str
    recovery_name: str
    final_value: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    return_to_drawdown: Decimal
    emergency_exits: int
    normal_trades: int
    cash_bars: int
    max_recovery_bars: int
    false_exits: int
    final_cash: Decimal
    final_quantity: Decimal
    final_phase: str
    events: tuple[CrashEvent, ...]


def select_strategy_action(
    phase: str,
    rsi_value: float | None,
    quantity: Decimal,
    cash: Decimal,
) -> str | None:
    if rsi_value is None:
        return None
    if rsi_value >= 65 and quantity > 0:
        return "sell_2"
    if rsi_value >= 60 and quantity > 0 and phase != "sell_2":
        return "sell_1"
    if phase == "buy_2":
        if rsi_value <= 40 and cash > 0:
            return "buy_2"
        return None
    if rsi_value <= 45 and cash > 0:
        return "buy_1"
    return None


def run_crash_backtest(
    candles: list[Candle],
    *,
    protection: ProtectionConfig | None,
    recovery: RecoveryConfig | None,
    fee_rate: Decimal = Decimal("0.0005"),
    normal_slippage_rate: Decimal = Decimal("0.0005"),
    crash_slippage_rate: Decimal = Decimal("0.003"),
    initial_krw: Decimal = Decimal("3000000"),
) -> CrashBacktestResult:
    if len(candles) < 15:
        raise ValueError("at least 15 candles are required")

    quantity = initial_krw / candles[0].open
    cash = Decimal("0")
    average_price = candles[0].open
    phase = "sell_1"
    pending: tuple[str, datetime] | None = None
    events: list[CrashEvent] = []
    peak = initial_krw
    max_drawdown = Decimal("0")
    cash_bars = 0
    normal_trades = 0
    rsi_values = rsi([float(candle.close) for candle in candles], period=14)

    for candle, rsi_value in zip(candles, rsi_values):
        if pending is not None:
            action, signal_timestamp = pending
            price = _execution_price(candle.open, action, normal_slippage_rate)
            traded_quantity = Decimal("0")
            if action == "sell_1":
                traded_quantity = quantity / Decimal("2")
                cash += traded_quantity * price * (Decimal("1") - fee_rate)
                quantity -= traded_quantity
                phase = "sell_2"
            elif action == "sell_2":
                traded_quantity = quantity
                cash += traded_quantity * price * (Decimal("1") - fee_rate)
                quantity = Decimal("0")
                average_price = Decimal("0")
                phase = "buy_1"
            elif action in {"buy_1", "buy_2"}:
                spend = cash / Decimal("2") if action == "buy_1" else cash
                bought = spend / (Decimal("1") + fee_rate) / price
                average_price = _weighted_average_price(quantity, average_price, bought, spend)
                quantity += bought
                cash -= spend
                traded_quantity = bought
                phase = "buy_2" if action == "buy_1" else "sell_1"
            else:
                raise ValueError(f"unsupported action: {action}")
            normal_trades += 1
            events.append(
                CrashEvent(
                    action=action,
                    signal_timestamp=signal_timestamp,
                    timestamp=candle.timestamp,
                    price=price,
                    quantity=traded_quantity,
                    cash=cash,
                    remaining_quantity=quantity,
                    phase=phase,
                )
            )
            pending = None

        value = cash + quantity * candle.close
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * Decimal("100"))
        if quantity == 0:
            cash_bars += 1

        action = select_strategy_action(phase, rsi_value, quantity, cash)
        if action is not None:
            pending = (action, candle.timestamp)

    final_value = cash + quantity * candles[-1].close
    return_pct = (final_value - initial_krw) / initial_krw * Decimal("100")
    ratio = return_pct / max_drawdown if max_drawdown > 0 else Decimal("0")
    return CrashBacktestResult(
        protection_name=protection.name if protection else "none",
        recovery_name=recovery.name if recovery else "none",
        final_value=final_value,
        return_pct=return_pct,
        max_drawdown_pct=max_drawdown,
        return_to_drawdown=ratio,
        emergency_exits=0,
        normal_trades=normal_trades,
        cash_bars=cash_bars,
        max_recovery_bars=0,
        false_exits=0,
        final_cash=cash,
        final_quantity=quantity,
        final_phase=phase,
        events=tuple(events),
    )


def _execution_price(open_price: Decimal, action: str, slippage_rate: Decimal) -> Decimal:
    if action.startswith("sell"):
        return open_price * (Decimal("1") - slippage_rate)
    return open_price * (Decimal("1") + slippage_rate)


def _weighted_average_price(
    current_quantity: Decimal,
    current_average_price: Decimal,
    bought_quantity: Decimal,
    spend: Decimal,
) -> Decimal:
    total_quantity = current_quantity + bought_quantity
    if total_quantity == 0:
        return Decimal("0")
    return (current_quantity * current_average_price + spend) / total_quantity
