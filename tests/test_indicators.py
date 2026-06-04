from huntbot.indicators import rsi


def test_rsi_returns_none_until_period_is_available():
    values = rsi([100, 101, 102, 103, 104], period=14)
    assert values == [None, None, None, None, None]


def test_rsi_handles_flat_prices_as_neutral():
    values = rsi([100] * 20, period=14)
    assert values[14] == 50.0
    assert values[-1] == 50.0


def test_rsi_returns_high_value_for_consistent_gains():
    values = rsi([100 + index for index in range(20)], period=14)
    assert values[-1] == 100.0
