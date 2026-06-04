from decimal import Decimal

from huntbot.indicators import rsi
from huntbot.models import BacktestResult, Candle
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
