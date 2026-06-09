from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.models import Candle
from huntbot.risk import evaluate_crash_risk


NOW = datetime(2026, 6, 9, 3, 0, tzinfo=timezone.utc)


def candles(highs):
    return [
        Candle(
            market="KRW-HUNT",
            unit=1,
            timestamp=NOW - timedelta(minutes=4 - index),
            open=Decimal("100"),
            high=Decimal(str(high)),
            low=Decimal("90"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )
        for index, high in enumerate(highs)
    ]


def test_seven_percent_below_recent_high_is_risky():
    result = evaluate_crash_risk(
        minute_candles=candles([100, 105, 110, 108, 107]),
        current_price=Decimal("102.3"),
        average_buy_price=Decimal("0"),
        previous_confirmations=0,
        now=NOW,
    )
    assert result.risky is True
    assert result.reason == "five_minute_high"
    assert result.confirmations == 1
    assert result.high_drop_pct == Decimal("7.00")


def test_ten_percent_below_average_buy_price_is_risky():
    result = evaluate_crash_risk(
        minute_candles=candles([95, 95, 95, 95, 95]),
        current_price=Decimal("90"),
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    assert result.risky is True
    assert result.confirmed is True
    assert result.reason == "average_buy_price"
    assert result.average_loss_pct == Decimal("10.0")


def test_healthy_observation_resets_confirmations():
    result = evaluate_crash_risk(
        minute_candles=candles([100, 100, 100, 100, 100]),
        current_price=Decimal("99"),
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    assert result.risky is False
    assert result.confirmations == 0
    assert result.confirmed is False


def test_insufficient_or_stale_candles_return_data_error():
    short = evaluate_crash_risk(
        minute_candles=candles([100, 100, 100, 100]),
        current_price=Decimal("90"),
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    stale_candles = [
        Candle(**{**candle.__dict__, "timestamp": NOW - timedelta(minutes=10 - index)})
        for index, candle in enumerate(candles([100, 100, 100, 100, 100]))
    ]
    stale = evaluate_crash_risk(
        minute_candles=stale_candles,
        current_price=Decimal("90"),
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    assert short.data_error == "insufficient_minute_candles"
    assert stale.data_error == "stale_minute_candles"
    assert short.confirmations == 0
    assert stale.confirmations == 0


def test_sparse_five_candles_do_not_form_a_five_minute_window():
    sparse = candles([100, 100, 100, 100, 100])
    sparse[0] = Candle(**{**sparse[0].__dict__, "timestamp": NOW - timedelta(minutes=12)})

    result = evaluate_crash_risk(
        minute_candles=sparse,
        current_price=Decimal("90"),
        average_buy_price=Decimal("100"),
        previous_confirmations=0,
        now=NOW,
    )

    assert result.data_error == "incomplete_five_minute_window"
