from decimal import Decimal

from huntbot.dashboard_metrics import calculate_performance


def _trade(action, side, quantity, funds, fee, timestamp):
    return {
        "uuid": f"{action}-{timestamp}",
        "action": action,
        "side": side,
        "executed_volume": Decimal(quantity),
        "executed_funds": Decimal(funds),
        "paid_fee": Decimal(fee),
        "completed_at": timestamp,
    }


def test_performance_uses_fees_and_moving_average_cost():
    trades = [
        _trade("buy_1", "buy", "10", "1000", "0.5", "2026-06-10T01:00:00+00:00"),
        _trade("buy_2", "buy", "10", "1200", "0.6", "2026-06-10T02:00:00+00:00"),
        _trade("sell_1", "sell", "5", "650", "0.325", "2026-06-10T03:00:00+00:00"),
    ]

    result = calculate_performance(
        trades,
        current_hunt=Decimal("15"),
        average_buy_price=Decimal("110"),
        best_bid=Decimal("130"),
    )

    assert result.cumulative_buy == Decimal("2200")
    assert result.cumulative_sell == Decimal("650")
    assert result.total_fees == Decimal("1.425")
    assert result.realized_pnl == Decimal("99.4")
    assert result.unrealized_pnl == Decimal("300")
    assert result.total_pnl == Decimal("399.4")
    assert result.is_partial is False


def test_sell_without_known_inventory_marks_realized_pnl_partial():
    trades = [
        _trade("sell_1", "sell", "5", "650", "0.325", "2026-06-10T03:00:00+00:00"),
    ]

    result = calculate_performance(
        trades,
        current_hunt=Decimal("0"),
        average_buy_price=Decimal("0"),
        best_bid=Decimal("130"),
    )

    assert result.realized_pnl == Decimal("0")
    assert result.unmatched_sell_quantity == Decimal("5")
    assert result.is_partial is True


def test_drawdown_requires_enough_time_span():
    short = calculate_performance(
        [],
        current_hunt=Decimal("0"),
        average_buy_price=Decimal("0"),
        best_bid=Decimal("0"),
        account_values=[
            ("2026-06-10T01:00:00+00:00", Decimal("100")),
            ("2026-06-10T01:30:00+00:00", Decimal("80")),
        ],
    )
    enough = calculate_performance(
        [],
        current_hunt=Decimal("0"),
        average_buy_price=Decimal("0"),
        best_bid=Decimal("0"),
        account_values=[
            ("2026-06-10T01:00:00+00:00", Decimal("100")),
            ("2026-06-10T02:00:00+00:00", Decimal("80")),
        ],
    )

    assert short.max_drawdown_pct is None
    assert enough.max_drawdown_pct == Decimal("20")
