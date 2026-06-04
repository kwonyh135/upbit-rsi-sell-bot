from decimal import Decimal

from huntbot.strategy import CycleState, evaluate_sell_signal


def test_first_overheat_signal_sells_when_value_is_large_enough():
    decision = evaluate_sell_signal(
        rsi_value=75.0,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("3000000"),
        available_quantity=Decimal("1000"),
        cycle=CycleState(ready=True),
    )
    assert decision.should_sell is True
    assert decision.sell_quantity == Decimal("500")
    assert decision.next_cycle.ready is False


def test_repeated_overheat_does_not_sell_before_reset():
    decision = evaluate_sell_signal(
        rsi_value=78.0,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("2000000"),
        available_quantity=Decimal("500"),
        cycle=CycleState(ready=False),
    )
    assert decision.should_sell is False
    assert decision.next_cycle.ready is False


def test_reset_below_threshold_allows_next_sell_later():
    reset_decision = evaluate_sell_signal(
        rsi_value=67.9,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("2000000"),
        available_quantity=Decimal("500"),
        cycle=CycleState(ready=False),
    )
    assert reset_decision.should_sell is False
    assert reset_decision.next_cycle.ready is True


def test_value_below_500000_blocks_sell():
    decision = evaluate_sell_signal(
        rsi_value=80.0,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("499999"),
        available_quantity=Decimal("100"),
        cycle=CycleState(ready=True),
    )
    assert decision.should_sell is False
    assert decision.reason == "holding_value_below_minimum"
