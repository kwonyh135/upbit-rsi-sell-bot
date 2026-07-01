from decimal import Decimal

from huntbot.indicators import WilderRsiPreview, rsi
from huntbot.intrabar_signals import provisional_rsi


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


def test_streaming_rsi_previews_match_full_history_through_warmup():
    prices = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105, 95, 106, 94, 107, 93, 108]
    closes = [Decimal(str(value)) for value in prices]
    preview = WilderRsiPreview(period=14)
    completed: list[Decimal] = []

    for close in closes:
        assert preview.preview(close) == provisional_rsi(completed, close, period=14)
        preview.append(close)
        completed.append(close)


def test_streaming_rsi_previews_match_full_history_for_long_mixed_sequence():
    closes = [
        Decimal(100 + ((index * 17) % 31) - ((index * 7) % 13))
        for index in range(500)
    ]
    preview = WilderRsiPreview(period=14)
    completed: list[Decimal] = []

    for close in closes:
        candidates = (close - Decimal("0.75"), close, close + Decimal("1.25"))
        expected = [
            provisional_rsi(completed, candidate, period=14)
            for candidate in candidates
        ]
        assert [preview.preview(candidate) for candidate in candidates] == expected
        preview.append(close)
        completed.append(close)


def test_streaming_rsi_state_is_bounded_and_preview_does_not_mutate_it():
    preview = WilderRsiPreview(period=14)
    for index in range(10_000):
        preview.append(Decimal(100 + index % 19))

    before = vars(preview).copy()
    preview.preview(Decimal("123.456"))

    assert vars(preview) == before
    assert not any(
        isinstance(value, (list, tuple, dict, set))
        for value in vars(preview).values()
    )
