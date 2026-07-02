from dataclasses import replace
from datetime import datetime

from huntbot.auto_state import AutoTradeState


def clear_rsi_confirmation(state: AutoTradeState) -> AutoTradeState:
    if not any(
        (
            state.rsi_signal_action,
            state.rsi_signal_started_at,
            state.rsi_signal_last_seen_at,
            state.rsi_signal_candle,
        )
    ):
        return state
    return replace(
        state,
        rsi_signal_action=None,
        rsi_signal_started_at=None,
        rsi_signal_last_seen_at=None,
        rsi_signal_candle=None,
    )


def update_rsi_confirmation(
    state: AutoTradeState,
    *,
    candidate_action: str | None,
    candidate_candle: str | None,
    now: datetime,
    hold_seconds: int = 30,
    max_gap_seconds: int = 20,
) -> tuple[AutoTradeState, str | None]:
    if candidate_action is None or candidate_candle is None:
        return clear_rsi_confirmation(state), None
    if candidate_candle == state.last_completed_candle:
        return clear_rsi_confirmation(state), None

    started_at = _parse_timestamp(state.rsi_signal_started_at)
    last_seen_at = _parse_timestamp(state.rsi_signal_last_seen_at)
    same_candidate = (
        state.rsi_signal_action == candidate_action
        and state.rsi_signal_candle is not None
        and started_at is not None
        and last_seen_at is not None
    )
    if same_candidate:
        gap_seconds = (now - last_seen_at).total_seconds()
        elapsed_seconds = (now - started_at).total_seconds()
        if 0 <= gap_seconds <= max_gap_seconds and elapsed_seconds >= 0:
            observed = replace(state, rsi_signal_last_seen_at=now.isoformat())
            ready_candle = (
                state.rsi_signal_candle
                if elapsed_seconds >= hold_seconds
                else None
            )
            return observed, ready_candle

    timestamp = now.isoformat()
    return (
        replace(
            state,
            rsi_signal_action=candidate_action,
            rsi_signal_started_at=timestamp,
            rsi_signal_last_seen_at=timestamp,
            rsi_signal_candle=candidate_candle,
        ),
        None,
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
