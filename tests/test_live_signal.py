from datetime import datetime, timedelta, timezone

from huntbot.auto_state import AutoTradeState
from huntbot.live_signal import clear_rsi_confirmation, update_rsi_confirmation


START = datetime(2026, 7, 2, tzinfo=timezone.utc)


def observe(state, second, *, action="buy_1", candle="c1"):
    return update_rsi_confirmation(
        state,
        candidate_action=action,
        candidate_candle=candle,
        now=START + timedelta(seconds=second),
    )


def test_same_candidate_becomes_ready_only_after_thirty_seconds():
    state, ready = observe(AutoTradeState(), 0)
    assert ready is None

    state, ready = observe(state, 10)
    assert ready is None
    state, ready = observe(state, 20)
    assert ready is None
    state, ready = observe(state, 30)

    assert ready == "c1"
    assert state.rsi_signal_last_seen_at == (START + timedelta(seconds=30)).isoformat()


def test_threshold_loss_clears_confirmation():
    state, _ = observe(AutoTradeState(), 0)

    state, ready = observe(state, 10, action=None, candle=None)

    assert ready is None
    assert state == AutoTradeState()


def test_action_change_restarts_confirmation():
    state, _ = observe(AutoTradeState(), 0, action="buy_1")

    state, ready = observe(state, 15, action="sell_1")

    assert ready is None
    assert state.rsi_signal_action == "sell_1"
    assert state.rsi_signal_started_at == (START + timedelta(seconds=15)).isoformat()


def test_observation_gap_over_twenty_seconds_restarts_confirmation():
    state, _ = observe(AutoTradeState(), 0)

    state, ready = observe(state, 21)

    assert ready is None
    assert state.rsi_signal_started_at == (START + timedelta(seconds=21)).isoformat()


def test_same_action_continues_across_candle_boundary():
    state, _ = observe(AutoTradeState(), 0, candle="c1")
    state, _ = observe(state, 10, candle="c1")
    state, _ = observe(state, 20, candle="c2")

    state, ready = observe(state, 30, candle="c2")

    assert ready == "c1"
    assert state.rsi_signal_candle == "c1"


def test_consumed_signal_candle_does_not_start_again():
    state = AutoTradeState(last_completed_candle="c1")

    state, ready = observe(state, 0, candle="c1")

    assert ready is None
    assert state.rsi_signal_action is None


def test_malformed_persisted_timestamp_restarts_safely():
    state = AutoTradeState(
        rsi_signal_action="buy_1",
        rsi_signal_started_at="not-a-time",
        rsi_signal_last_seen_at="also-bad",
        rsi_signal_candle="c1",
    )

    state, ready = observe(state, 30)

    assert ready is None
    assert state.rsi_signal_started_at == (START + timedelta(seconds=30)).isoformat()


def test_clear_only_removes_rsi_confirmation_fields():
    state = AutoTradeState(
        phase="buy_2",
        emergency_confirmations=1,
        emergency_reason="five_minute_high",
        rsi_signal_action="buy_1",
        rsi_signal_started_at=START.isoformat(),
        rsi_signal_last_seen_at=START.isoformat(),
        rsi_signal_candle="c1",
    )

    cleared = clear_rsi_confirmation(state)

    assert cleared.phase == "buy_2"
    assert cleared.emergency_confirmations == 1
    assert cleared.emergency_reason == "five_minute_high"
    assert cleared.rsi_signal_action is None
