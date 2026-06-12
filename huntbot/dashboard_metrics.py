from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PerformanceSummary:
    cumulative_buy: Decimal
    cumulative_sell: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    return_pct: Decimal | None
    total_fees: Decimal
    buy_count: int
    sell_count: int
    average_buy_price: Decimal | None
    average_sell_price: Decimal | None
    unmatched_sell_quantity: Decimal
    is_partial: bool
    max_drawdown_pct: Decimal | None
    realized_curve: tuple[tuple[str, Decimal], ...]
    trade_details: tuple[dict, ...]


def calculate_performance(
    trades: list[dict],
    *,
    current_hunt: Decimal,
    average_buy_price: Decimal,
    best_bid: Decimal,
    account_values: list[tuple[str, Decimal]] | None = None,
) -> PerformanceSummary:
    quantity = Decimal("0")
    inventory_cost = Decimal("0")
    cumulative_buy = Decimal("0")
    cumulative_sell = Decimal("0")
    realized = Decimal("0")
    fees = Decimal("0")
    buy_volume = Decimal("0")
    sell_volume = Decimal("0")
    unmatched = Decimal("0")
    buy_count = 0
    sell_count = 0
    realized_curve = []
    trade_details = []

    ordered = sorted(
        trades,
        key=lambda item: item.get("completed_at") or item.get("created_at") or "",
    )
    for trade in ordered:
        volume = Decimal(str(trade.get("executed_volume", "0")))
        funds = Decimal(str(trade.get("executed_funds", "0")))
        fee = Decimal(str(trade.get("paid_fee", "0")))
        fees += fee
        if trade.get("side") == "buy":
            cumulative_buy += funds
            buy_volume += volume
            buy_count += 1
            quantity += volume
            inventory_cost += funds + fee
            trade_details.append(
                {
                    "uuid": trade.get("uuid", ""),
                    "timestamp": trade.get("completed_at")
                    or trade.get("created_at")
                    or "",
                    "action": trade.get("action", ""),
                    "side": "buy",
                    "execution_price": (
                        funds / volume if volume > 0 else Decimal("0")
                    ),
                    "quantity": volume,
                    "gross_amount": funds,
                    "fee": fee,
                    "cost_basis_price": None,
                    "realized_pnl": None,
                }
            )
        else:
            cumulative_sell += funds
            sell_volume += volume
            sell_count += 1
            matched = min(quantity, volume)
            unit_cost = inventory_cost / quantity if quantity > 0 else None
            trade_realized = Decimal("0")
            if matched > 0 and quantity > 0:
                proceeds = (funds - fee) * (matched / volume) if volume > 0 else Decimal("0")
                trade_realized = proceeds - unit_cost * matched
                realized += trade_realized
                inventory_cost -= unit_cost * matched
                quantity -= matched
            unmatched += volume - matched
            timestamp = (
                trade.get("completed_at") or trade.get("created_at") or ""
            )
            trade_details.append(
                {
                    "uuid": trade.get("uuid", ""),
                    "timestamp": timestamp,
                    "action": trade.get("action", ""),
                    "side": "sell",
                    "execution_price": (
                        funds / volume if volume > 0 else Decimal("0")
                    ),
                    "quantity": volume,
                    "gross_amount": funds,
                    "fee": fee,
                    "cost_basis_price": unit_cost,
                    "realized_pnl": trade_realized,
                }
            )
            realized_curve.append((timestamp, realized))

    unrealized = current_hunt * (best_bid - average_buy_price)
    total_pnl = realized + unrealized
    return_pct = (
        total_pnl / cumulative_buy * Decimal("100")
        if cumulative_buy > 0
        else None
    )
    average_buy = cumulative_buy / buy_volume if buy_volume > 0 else None
    average_sell = cumulative_sell / sell_volume if sell_volume > 0 else None

    return PerformanceSummary(
        cumulative_buy=cumulative_buy,
        cumulative_sell=cumulative_sell,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=total_pnl,
        return_pct=return_pct,
        total_fees=fees,
        buy_count=buy_count,
        sell_count=sell_count,
        average_buy_price=average_buy,
        average_sell_price=average_sell,
        unmatched_sell_quantity=unmatched,
        is_partial=unmatched > 0,
        max_drawdown_pct=_max_drawdown(account_values or []),
        realized_curve=tuple(realized_curve),
        trade_details=tuple(trade_details),
    )


def _max_drawdown(values: list[tuple[str, Decimal]]) -> Decimal | None:
    if len(values) < 2:
        return None
    start = datetime.fromisoformat(values[0][0])
    end = datetime.fromisoformat(values[-1][0])
    if (end - start).total_seconds() < 3600:
        return None
    peak = Decimal("0")
    maximum = Decimal("0")
    for _, value in values:
        peak = max(peak, value)
        if peak > 0:
            maximum = max(maximum, (peak - value) / peak * Decimal("100"))
    return maximum
