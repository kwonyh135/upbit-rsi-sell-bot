from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.models import Candle


def _candle(timestamp, *, open_price, high, low, close):
    return Candle(
        market="BTCUSDT",
        unit=5,
        timestamp=timestamp,
        open=Decimal(str(open_price)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1"),
    )


def _four_hour_bucket(start, *, open_price, high, low, close):
    candles = []
    for index in range(48):
        timestamp = start + timedelta(minutes=5 * index)
        price = Decimal(str(open_price))
        candles.append(_candle(timestamp, open_price=price, high=price, low=price, close=price))
    candles[-1] = _candle(start + timedelta(minutes=235), open_price=open_price, high=high, low=low, close=close)
    return candles


def test_paper_cycle_opens_long_on_new_donchian_breakout(tmp_path):
    from huntbot.bitget_paper_trader import PaperConfig, PaperState, run_paper_cycle

    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    candles = (
        _four_hour_bucket(start, open_price=100, high=101, low=99, close=100)
        + _four_hour_bucket(start + timedelta(hours=4), open_price=100, high=102, low=99, close=101)
        + _four_hour_bucket(start + timedelta(hours=8), open_price=103, high=104, low=102, close=103)
    )

    result = run_paper_cycle(
        candles,
        PaperState(),
        PaperConfig(lookback=2, initial_equity=Decimal("1000")),
        state_path=tmp_path / "paper.json",
    )

    assert result.action == "open_long"
    assert result.state.position == "long"
    assert result.state.quantity > 0
    assert result.state.last_signal_timestamp == start + timedelta(hours=12)
    assert len(result.state.trades) == 1


def test_paper_cycle_does_not_repeat_same_signal(tmp_path):
    from huntbot.bitget_paper_trader import PaperConfig, PaperState, run_paper_cycle

    signal_time = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    state = PaperState(last_signal_timestamp=signal_time, position="long", quantity=Decimal("1"), cash=Decimal("-1"))

    result = run_paper_cycle(
        [
            *_four_hour_bucket(datetime(2026, 7, 1, tzinfo=timezone.utc), open_price=100, high=101, low=99, close=100),
            *_four_hour_bucket(datetime(2026, 7, 1, 4, tzinfo=timezone.utc), open_price=100, high=102, low=99, close=101),
            *_four_hour_bucket(datetime(2026, 7, 1, 8, tzinfo=timezone.utc), open_price=103, high=104, low=102, close=103),
        ],
        state,
        PaperConfig(lookback=2),
        state_path=tmp_path / "paper.json",
    )

    assert result.action is None
    assert len(result.state.trades) == 0


def test_paper_state_round_trips_json(tmp_path):
    from huntbot.bitget_paper_trader import PaperState, PaperTrade, load_paper_state, save_paper_state

    path = tmp_path / "paper.json"
    original = PaperState(
        position="short",
        cash=Decimal("2000.5"),
        quantity=Decimal("-0.25"),
        last_signal_timestamp=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        trades=(
            PaperTrade(
                timestamp=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
                action="open_short",
                price=Decimal("60000"),
                quantity=Decimal("-0.25"),
                fee=Decimal("9"),
                equity=Decimal("1991.5"),
            ),
        ),
    )

    save_paper_state(original, path)

    assert load_paper_state(path) == original
