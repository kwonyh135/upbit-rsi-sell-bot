from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.config import EMERGENCY_AVG_LOSS_PCT
from huntbot.models import Candle
from huntbot.risk import evaluate_completed_candle_crash_risk, evaluate_crash_risk


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


def five_minute_candle(timestamp, *, high, close):
    return Candle(
        market="KRW-HUNT",
        unit=5,
        timestamp=timestamp,
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1"),
    )


def test_completed_candle_six_percent_high_drop_boundary_is_risky():
    candle = five_minute_candle(NOW - timedelta(minutes=5), high="100", close="94")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[candle],
        average_buy_price=Decimal("0"),
        now=NOW,
    )

    assert result.risky is True
    assert result.confirmed is False
    assert result.confirmations == 1
    assert result.high_drop_pct == Decimal("6.00")
    assert result.reason == "five_minute_high"


def test_completed_candle_twelve_percent_average_loss_boundary_is_risky():
    candle = five_minute_candle(NOW - timedelta(minutes=5), high="88", close="88")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[candle],
        average_buy_price=Decimal("100"),
        now=NOW,
    )

    assert result.risky is True
    assert EMERGENCY_AVG_LOSS_PCT == Decimal("12")
    assert result.average_loss_pct == Decimal("12.00")
    assert result.reason == "average_buy_price"


def test_completed_candle_average_loss_below_twelve_percent_is_healthy():
    candle = five_minute_candle(NOW - timedelta(minutes=5), high="88.01", close="88.01")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[candle],
        average_buy_price=Decimal("100"),
        now=NOW,
    )

    assert result.risky is False
    assert result.confirmations == 0


def test_completed_candle_values_below_boundaries_are_healthy():
    candle = five_minute_candle(NOW - timedelta(minutes=5), high="100", close="94.01")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[candle],
        average_buy_price=Decimal("98.95"),
        now=NOW,
    )

    assert result.risky is False
    assert result.confirmations == 0


def test_only_completed_five_minute_candles_are_considered():
    completed = five_minute_candle(NOW - timedelta(minutes=10), high="100", close="100")
    in_progress = five_minute_candle(NOW - timedelta(minutes=2), high="100", close="90")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[completed, in_progress],
        average_buy_price=Decimal("0"),
        now=NOW,
    )

    assert result.risky is False
    assert result.confirmations == 0


def test_two_adjacent_risky_completed_candles_confirm_emergency():
    previous = five_minute_candle(NOW - timedelta(minutes=10), high="100", close="94")
    latest = five_minute_candle(NOW - timedelta(minutes=5), high="100", close="93")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[previous, latest],
        average_buy_price=Decimal("0"),
        now=NOW,
    )

    assert result.risky is True
    assert result.confirmed is True
    assert result.confirmations == 2


def test_timestamp_gap_breaks_completed_candle_confirmation():
    previous = five_minute_candle(NOW - timedelta(minutes=15), high="100", close="94")
    latest = five_minute_candle(NOW - timedelta(minutes=5), high="100", close="93")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[previous, latest],
        average_buy_price=Decimal("0"),
        now=NOW,
    )

    assert result.risky is True
    assert result.confirmed is False
    assert result.confirmations == 1


def test_healthy_latest_completed_candle_resets_confirmation():
    previous = five_minute_candle(NOW - timedelta(minutes=10), high="100", close="94")
    latest = five_minute_candle(NOW - timedelta(minutes=5), high="100", close="99")

    result = evaluate_completed_candle_crash_risk(
        five_minute_candles=[previous, latest],
        average_buy_price=Decimal("0"),
        now=NOW,
    )

    assert result.risky is False
    assert result.confirmations == 0


def test_seven_percent_below_recent_high_is_risky():
    result = evaluate_crash_risk(
        minute_candles=candles([100, 105, 110, 108, 107]),
        current_price=Decimal("102.3"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("0"),
        previous_confirmations=0,
        now=NOW,
    )
    assert result.risky is True
    assert result.reason == "five_minute_high"
    assert result.confirmations == 1
    assert result.high_drop_pct == Decimal("7.00")


def test_twelve_percent_below_average_buy_price_is_risky():
    result = evaluate_crash_risk(
        minute_candles=candles([88, 88, 88, 88, 88]),
        current_price=Decimal("88"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    assert result.risky is True
    assert result.confirmed is True
    assert result.reason == "average_buy_price"
    assert result.average_loss_pct == Decimal("12.00")


def test_healthy_observation_resets_confirmations():
    result = evaluate_crash_risk(
        minute_candles=candles([100, 100, 100, 100, 100]),
        current_price=Decimal("99"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    assert result.risky is False
    assert result.confirmations == 0
    assert result.confirmed is False


def test_invalid_or_stale_orderbook_price_returns_data_error():
    invalid = evaluate_crash_risk(
        minute_candles=[],
        current_price=Decimal("0"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    stale = evaluate_crash_risk(
        minute_candles=[],
        current_price=Decimal("88"),
        current_price_timestamp=NOW - timedelta(minutes=3),
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )
    assert invalid.data_error == "invalid_current_price"
    assert stale.data_error == "stale_current_price"
    assert invalid.confirmations == 0
    assert stale.confirmations == 0


def test_old_candles_are_ignored_instead_of_extending_the_window():
    sparse = candles([100, 100, 100, 100, 100])
    sparse = [
        Candle(**{**candle.__dict__, "timestamp": NOW - timedelta(minutes=12 + index)})
        for index, candle in enumerate(sparse)
    ]

    result = evaluate_crash_risk(
        minute_candles=sparse,
        current_price=Decimal("90"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("0"),
        previous_confirmations=0,
        now=NOW,
    )

    assert result.data_error is None
    assert result.risky is False
    assert result.high_drop_pct == Decimal("0")


def test_gapped_candles_use_only_highs_inside_five_minute_window():
    recent = candles([150, 140, 120, 115, 112])
    recent[0] = Candle(**{**recent[0].__dict__, "timestamp": NOW - timedelta(minutes=20)})
    recent[1] = Candle(**{**recent[1].__dict__, "timestamp": NOW - timedelta(minutes=10)})

    result = evaluate_crash_risk(
        minute_candles=recent,
        current_price=Decimal("111.6"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("0"),
        previous_confirmations=0,
        now=NOW,
    )

    assert result.data_error is None
    assert result.risky is True
    assert result.high_drop_pct == Decimal("7.00")


def test_stale_trade_candles_still_check_average_with_fresh_orderbook_price():
    stale = [
        Candle(**{**candle.__dict__, "timestamp": NOW - timedelta(minutes=20 - index)})
        for index, candle in enumerate(candles([120, 120, 120, 120, 120]))
    ]

    result = evaluate_crash_risk(
        minute_candles=stale,
        current_price=Decimal("88"),
        current_price_timestamp=NOW,
        average_buy_price=Decimal("100"),
        previous_confirmations=1,
        now=NOW,
    )

    assert result.data_error is None
    assert result.confirmed is True
    assert result.reason == "average_buy_price"
