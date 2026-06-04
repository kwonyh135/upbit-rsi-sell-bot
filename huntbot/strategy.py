from dataclasses import dataclass
from decimal import Decimal


MIN_HOLDING_VALUE_KRW = Decimal("500000")


@dataclass(frozen=True)
class CycleState:
    ready: bool = True


@dataclass(frozen=True)
class SellDecision:
    should_sell: bool
    sell_quantity: Decimal
    reason: str
    next_cycle: CycleState


def evaluate_sell_signal(
    *,
    rsi_value: float | None,
    sell_rsi: float,
    reset_rsi: float,
    holding_value: Decimal,
    available_quantity: Decimal,
    cycle: CycleState,
) -> SellDecision:
    if rsi_value is None:
        return SellDecision(False, Decimal("0"), "rsi_unavailable", cycle)
    if holding_value < MIN_HOLDING_VALUE_KRW:
        return SellDecision(False, Decimal("0"), "holding_value_below_minimum", cycle)
    if rsi_value < reset_rsi:
        return SellDecision(False, Decimal("0"), "reset_ready", CycleState(ready=True))
    if rsi_value >= sell_rsi and cycle.ready:
        return SellDecision(True, available_quantity / Decimal("2"), "sell_signal", CycleState(ready=False))
    if rsi_value >= sell_rsi:
        return SellDecision(False, Decimal("0"), "already_sold_this_cycle", cycle)
    return SellDecision(False, Decimal("0"), "waiting", cycle)
