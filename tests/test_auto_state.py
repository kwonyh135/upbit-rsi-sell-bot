import json
from decimal import Decimal

from huntbot.auto_state import AutoTradeState, PendingOrder, load_auto_state, save_auto_state


def test_auto_state_round_trip_preserves_pending_order(tmp_path):
    path = tmp_path / "auto.json"
    state = AutoTradeState(
        phase="buy_2",
        last_completed_candle="2026-06-09T01:00:00+00:00",
        pending_order=PendingOrder(
            identifier="huntbot-buy-1",
            action="buy_2",
            next_phase="sell_1",
            candle_timestamp="2026-06-09T01:00:00+00:00",
            rsi_value=39.5,
            requested_amount=Decimal("12345.67"),
            uuid="order-1",
        ),
        emergency_confirmations=1,
        emergency_reason="five_minute_high",
    )

    save_auto_state(state, path)

    assert load_auto_state(path) == state


def test_auto_state_defaults_when_file_is_missing(tmp_path):
    assert load_auto_state(tmp_path / "missing.json") == AutoTradeState()


def test_legacy_auto_state_defaults_rsi_confirmation_to_empty(tmp_path):
    path = tmp_path / "auto.json"
    path.write_text('{"phase": "buy_1"}', encoding="utf-8")

    state = load_auto_state(path)

    assert state.rsi_signal_action is None
    assert state.rsi_signal_started_at is None
    assert state.rsi_signal_last_seen_at is None
    assert state.rsi_signal_candle is None


def test_auto_state_round_trips_rsi_confirmation(tmp_path):
    path = tmp_path / "auto.json"
    state = AutoTradeState(
        phase="buy_1",
        rsi_signal_action="buy_1",
        rsi_signal_started_at="2026-07-02T00:00:00+00:00",
        rsi_signal_last_seen_at="2026-07-02T00:00:10+00:00",
        rsi_signal_candle="2026-07-02T00:00:00+00:00",
    )

    save_auto_state(state, path)

    assert load_auto_state(path) == state


def test_auto_state_save_replaces_existing_json(tmp_path):
    path = tmp_path / "auto.json"
    path.write_text('{"phase": "broken"}', encoding="utf-8")

    save_auto_state(AutoTradeState(phase="emergency_halt"), path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["phase"] == "emergency_halt"
    assert not list(tmp_path.glob("*.tmp"))
