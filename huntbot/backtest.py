from decimal import Decimal

from huntbot.indicators import rsi
from huntbot.models import BacktestResult, BuybackBacktestResult, Candle, SplitBuybackBacktestResult, TradeEvent
from huntbot.strategy import CycleState, evaluate_sell_signal


def run_backtest(
    candles: list[Candle],
    *,
    sell_rsi: float,
    reset_rsi: float,
    initial_krw: Decimal = Decimal("3000000"),
) -> BacktestResult:
    if len(candles) < 15:
        raise ValueError("at least 15 candles are required")

    first_price = candles[0].close
    quantity = initial_krw / first_price
    cash = Decimal("0")
    peak_value = initial_krw
    max_drawdown_pct = 0.0
    sell_count = 0
    cycle = CycleState(ready=True)
    rsi_values = rsi([float(candle.close) for candle in candles], period=14)

    for candle, rsi_value in zip(candles, rsi_values):
        holding_value = quantity * candle.close
        total_value = cash + holding_value
        if total_value > peak_value:
            peak_value = total_value
        drawdown = float((peak_value - total_value) / peak_value * Decimal("100"))
        max_drawdown_pct = max(max_drawdown_pct, drawdown)

        decision = evaluate_sell_signal(
            rsi_value=rsi_value,
            sell_rsi=sell_rsi,
            reset_rsi=reset_rsi,
            holding_value=holding_value,
            available_quantity=quantity,
            cycle=cycle,
        )
        cycle = decision.next_cycle
        if decision.should_sell:
            sell_quantity = decision.sell_quantity
            cash += sell_quantity * candle.close
            quantity -= sell_quantity
            sell_count += 1

    final_price = candles[-1].close
    final_total_value = cash + (quantity * final_price)
    final_return_pct = float((final_total_value - initial_krw) / initial_krw * Decimal("100"))

    return BacktestResult(
        unit=candles[0].unit,
        sell_rsi=sell_rsi,
        reset_rsi=reset_rsi,
        final_return_pct=round(final_return_pct, 6),
        final_total_value=final_total_value,
        sell_count=sell_count,
        remaining_quantity=quantity,
        cash=cash,
        max_drawdown_pct=round(max_drawdown_pct, 6),
    )


def run_candidate_search(candles_by_unit: dict[int, list[Candle]]) -> list[BacktestResult]:
    results: list[BacktestResult] = []
    reset_deltas = [3, 5, 7, 10, 15]
    for candles in candles_by_unit.values():
        for sell_rsi in range(65, 91):
            for delta in reset_deltas:
                reset_rsi = float(sell_rsi - delta)
                results.append(run_backtest(candles, sell_rsi=float(sell_rsi), reset_rsi=reset_rsi))
    return sorted(results, key=lambda item: item.final_return_pct, reverse=True)


def run_buyback_backtest(
    candles: list[Candle],
    *,
    sell_rsi: float,
    buy_rsi: float,
    initial_krw: Decimal = Decimal("3000000"),
) -> BuybackBacktestResult:
    if len(candles) < 15:
        raise ValueError("at least 15 candles are required")
    if buy_rsi >= sell_rsi:
        raise ValueError("buy_rsi must be lower than sell_rsi")

    first_price = candles[0].close
    quantity = initial_krw / first_price
    cash = Decimal("0")
    peak_value = initial_krw
    max_drawdown_pct = 0.0
    sell_count = 0
    buy_count = 0
    rsi_values = rsi([float(candle.close) for candle in candles], period=14)

    for candle, rsi_value in zip(candles, rsi_values):
        total_value = cash + (quantity * candle.close)
        if total_value > peak_value:
            peak_value = total_value
        drawdown = float((peak_value - total_value) / peak_value * Decimal("100"))
        max_drawdown_pct = max(max_drawdown_pct, drawdown)

        if rsi_value is None:
            continue
        if rsi_value >= sell_rsi and cash == 0 and quantity > 0:
            sell_quantity = quantity / Decimal("2")
            cash += sell_quantity * candle.close
            quantity -= sell_quantity
            sell_count += 1
        elif rsi_value <= buy_rsi and cash > 0:
            quantity += cash / candle.close
            cash = Decimal("0")
            buy_count += 1

    final_total_value = cash + (quantity * candles[-1].close)
    final_return_pct = float((final_total_value - initial_krw) / initial_krw * Decimal("100"))
    return BuybackBacktestResult(
        unit=candles[0].unit,
        sell_rsi=sell_rsi,
        buy_rsi=buy_rsi,
        final_return_pct=round(final_return_pct, 6),
        final_total_value=final_total_value,
        sell_count=sell_count,
        buy_count=buy_count,
        remaining_quantity=quantity,
        cash=cash,
        max_drawdown_pct=round(max_drawdown_pct, 6),
    )


def run_buyback_candidate_search(candles_by_unit: dict[int, list[Candle]]) -> list[BuybackBacktestResult]:
    results: list[BuybackBacktestResult] = []
    for candles in candles_by_unit.values():
        for sell_rsi in range(65, 91):
            for buy_rsi in range(20, 50):
                results.append(run_buyback_backtest(candles, sell_rsi=float(sell_rsi), buy_rsi=float(buy_rsi)))
    return sorted(results, key=lambda item: item.final_return_pct, reverse=True)


def run_split_buyback_backtest(
    candles: list[Candle],
    *,
    sell_rsi_1: float,
    sell_rsi_2: float,
    buy_rsi_1: float,
    buy_rsi_2: float,
    fee_rate: Decimal = Decimal("0.0005"),
    slippage_rate: Decimal = Decimal("0.0005"),
    initial_krw: Decimal = Decimal("3000000"),
) -> SplitBuybackBacktestResult:
    if len(candles) < 15:
        raise ValueError("at least 15 candles are required")
    if sell_rsi_1 >= sell_rsi_2:
        raise ValueError("sell_rsi_1 must be lower than sell_rsi_2")
    if buy_rsi_1 <= buy_rsi_2:
        raise ValueError("buy_rsi_1 must be higher than buy_rsi_2")

    first_price = candles[0].close
    quantity = initial_krw / first_price
    cash = Decimal("0")
    peak_value = initial_krw
    max_drawdown_pct = 0.0
    sell_count = 0
    buy_count = 0
    phase = "sell_1"
    events: list[TradeEvent] = []
    average_price = first_price
    rsi_values = rsi([float(candle.close) for candle in candles], period=14)

    for candle, rsi_value in zip(candles, rsi_values):
        total_value = cash + (quantity * candle.close)
        if total_value > peak_value:
            peak_value = total_value
        drawdown = float((peak_value - total_value) / peak_value * Decimal("100"))
        max_drawdown_pct = max(max_drawdown_pct, drawdown)

        if rsi_value is None:
            continue

        if phase == "sell_1" and rsi_value >= sell_rsi_1:
            sell_quantity = quantity / Decimal("2")
            sell_cash = _sell_cash(sell_quantity, candle.close, fee_rate, slippage_rate)
            realized_profit = sell_cash - (sell_quantity * average_price)
            cash += sell_cash
            quantity -= sell_quantity
            sell_count += 1
            events.append(
                _trade_event(
                    "sell_1",
                    candle,
                    rsi_value,
                    sell_quantity,
                    cash,
                    quantity,
                    fee_rate,
                    slippage_rate,
                    average_price,
                    realized_profit,
                )
            )
            phase = "sell_2"
        elif phase == "sell_2" and rsi_value >= sell_rsi_2:
            sell_quantity = quantity
            sell_cash = _sell_cash(sell_quantity, candle.close, fee_rate, slippage_rate)
            realized_profit = sell_cash - (sell_quantity * average_price)
            cash += sell_cash
            quantity = Decimal("0")
            sell_count += 1
            events.append(
                _trade_event(
                    "sell_2",
                    candle,
                    rsi_value,
                    sell_quantity,
                    cash,
                    quantity,
                    fee_rate,
                    slippage_rate,
                    average_price,
                    realized_profit,
                )
            )
            average_price = Decimal("0")
            phase = "buy_1"
        elif phase == "buy_1" and rsi_value <= buy_rsi_1:
            spend = cash / Decimal("2")
            bought_quantity = _buy_quantity(spend, candle.close, fee_rate, slippage_rate)
            average_price = _weighted_average_price(
                current_quantity=quantity,
                current_average_price=average_price,
                bought_quantity=bought_quantity,
                spend=spend,
            )
            quantity += bought_quantity
            cash -= spend
            buy_count += 1
            events.append(
                _trade_event(
                    "buy_1",
                    candle,
                    rsi_value,
                    bought_quantity,
                    cash,
                    quantity,
                    fee_rate,
                    slippage_rate,
                    average_price,
                    Decimal("0"),
                )
            )
            phase = "buy_2"
        elif phase == "buy_2" and rsi_value <= buy_rsi_2:
            spend = cash
            bought_quantity = _buy_quantity(spend, candle.close, fee_rate, slippage_rate)
            average_price = _weighted_average_price(
                current_quantity=quantity,
                current_average_price=average_price,
                bought_quantity=bought_quantity,
                spend=spend,
            )
            quantity += bought_quantity
            cash = Decimal("0")
            buy_count += 1
            events.append(
                _trade_event(
                    "buy_2",
                    candle,
                    rsi_value,
                    bought_quantity,
                    cash,
                    quantity,
                    fee_rate,
                    slippage_rate,
                    average_price,
                    Decimal("0"),
                )
            )
            phase = "sell_1"

    final_total_value = cash + (quantity * candles[-1].close)
    final_return_pct = float((final_total_value - initial_krw) / initial_krw * Decimal("100"))
    return SplitBuybackBacktestResult(
        unit=candles[0].unit,
        sell_rsi_1=sell_rsi_1,
        sell_rsi_2=sell_rsi_2,
        buy_rsi_1=buy_rsi_1,
        buy_rsi_2=buy_rsi_2,
        final_return_pct=round(final_return_pct, 6),
        final_total_value=final_total_value,
        sell_count=sell_count,
        buy_count=buy_count,
        remaining_quantity=quantity,
        cash=cash,
        max_drawdown_pct=round(max_drawdown_pct, 6),
        events=tuple(events),
    )


def run_split_buyback_candidate_search(candles_by_unit: dict[int, list[Candle]]) -> list[SplitBuybackBacktestResult]:
    results: list[SplitBuybackBacktestResult] = []
    for candles in candles_by_unit.values():
        for sell_rsi_1 in range(60, 76):
            for sell_delta in [5, 10, 15, 20]:
                sell_rsi_2 = float(sell_rsi_1 + sell_delta)
                if sell_rsi_2 > 90:
                    continue
                for buy_rsi_1 in range(45, 50):
                    for buy_delta in [5, 10, 15, 20]:
                        buy_rsi_2 = float(buy_rsi_1 - buy_delta)
                        if buy_rsi_2 < 20:
                            continue
                        results.append(
                            run_split_buyback_backtest(
                                candles,
                                sell_rsi_1=float(sell_rsi_1),
                                sell_rsi_2=sell_rsi_2,
                                buy_rsi_1=float(buy_rsi_1),
                                buy_rsi_2=buy_rsi_2,
                            )
                        )
    return sorted(results, key=lambda item: item.final_return_pct, reverse=True)


def _sell_cash(quantity: Decimal, close_price: Decimal, fee_rate: Decimal, slippage_rate: Decimal) -> Decimal:
    effective_price = close_price * (Decimal("1") - slippage_rate)
    gross = quantity * effective_price
    return gross * (Decimal("1") - fee_rate)


def _buy_quantity(krw_amount: Decimal, close_price: Decimal, fee_rate: Decimal, slippage_rate: Decimal) -> Decimal:
    trade_value = krw_amount / (Decimal("1") + fee_rate)
    effective_price = close_price * (Decimal("1") + slippage_rate)
    return trade_value / effective_price


def _weighted_average_price(
    *,
    current_quantity: Decimal,
    current_average_price: Decimal,
    bought_quantity: Decimal,
    spend: Decimal,
) -> Decimal:
    total_quantity = current_quantity + bought_quantity
    if total_quantity == 0:
        return Decimal("0")
    return ((current_quantity * current_average_price) + spend) / total_quantity


def _trade_event(
    action: str,
    candle: Candle,
    rsi_value: float,
    quantity: Decimal,
    cash: Decimal,
    remaining_quantity: Decimal,
    fee_rate: Decimal,
    slippage_rate: Decimal,
    average_price: Decimal,
    realized_profit: Decimal,
) -> TradeEvent:
    if action.startswith("sell"):
        effective_price = candle.close * (Decimal("1") - slippage_rate)
    else:
        effective_price = candle.close * (Decimal("1") + slippage_rate)
    total_value = cash + (remaining_quantity * candle.close)
    return TradeEvent(
        action=action,
        timestamp=candle.timestamp,
        unit=candle.unit,
        rsi_value=round(rsi_value, 6),
        close_price=candle.close,
        effective_price=effective_price,
        quantity=quantity,
        cash=cash,
        remaining_quantity=remaining_quantity,
        total_value=total_value,
        average_price=average_price,
        realized_profit=realized_profit,
    )
