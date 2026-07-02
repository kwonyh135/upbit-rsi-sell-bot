# Live RSI Hold-30-Seconds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make unattended live and dry-run normal RSI orders require a continuously observed provisional intrabar condition for 30 seconds.

**Architecture:** Extend the atomic auto-trading state with backward-compatible confirmation fields and place the pure timing transition in a focused `live_signal` module. `run_auto_cycle` retains pending-order and completed-candle emergency priority, then computes provisional RSI from completed closes plus the validated best bid and submits only a mature held signal.

**Tech Stack:** Python 3.12, frozen dataclasses, atomic JSON state, pytest, existing Upbit client and systemd deployment.

## Global Constraints

- Keep `KRW-HUNT`, RSI period 14, thresholds 60/65/45/40, split sizing, and Upbit minimum-order checks unchanged.
- Require 30 elapsed seconds with no observation gap greater than 20 seconds.
- Keep pending-order reconciliation and completed-candle 6%/12% two-candle emergency protection ahead of normal RSI.
- Never block the service loop with `sleep(30)`.
- Old state JSON must load without migration commands.
- Dry-run must never submit an order.
- Do not expose or modify `.env` secrets.

---

### Task 1: Persist And Evaluate Held Signals

**Files:**
- Modify: `huntbot/auto_state.py`
- Create: `huntbot/live_signal.py`
- Modify: `tests/test_auto_state.py`
- Create: `tests/test_live_signal.py`

**Interfaces:**
- Produces: `clear_rsi_confirmation(state: AutoTradeState) -> AutoTradeState`.
- Produces: `update_rsi_confirmation(state: AutoTradeState, *, candidate_action: str | None, candidate_candle: str | None, now: datetime, hold_seconds: int = 30, max_gap_seconds: int = 20) -> tuple[AutoTradeState, str | None]`; the second result is the original signal candle only when ready.

- [ ] **Step 1: Add failing backward-compatibility and round-trip tests**

```python
def test_legacy_auto_state_defaults_rsi_confirmation_to_empty(tmp_path):
    path = tmp_path / "auto.json"
    path.write_text('{"phase":"buy_1"}', encoding="utf-8")
    state = load_auto_state(path)
    assert state.rsi_signal_action is None
    assert state.rsi_signal_started_at is None
    assert state.rsi_signal_last_seen_at is None
    assert state.rsi_signal_candle is None


def test_auto_state_round_trips_rsi_confirmation(tmp_path):
    state = AutoTradeState(
        phase="buy_1",
        rsi_signal_action="buy_1",
        rsi_signal_started_at="2026-07-02T00:00:00+00:00",
        rsi_signal_last_seen_at="2026-07-02T00:00:10+00:00",
        rsi_signal_candle="2026-07-02T00:00:00+00:00",
    )
    save_auto_state(state, path)
    assert load_auto_state(path) == state
```

- [ ] **Step 2: Run state tests and verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_auto_state.py -q`

Expected: FAIL because the four confirmation fields do not exist.

- [ ] **Step 3: Add the four optional string fields to `AutoTradeState` and load them with `data.get("rsi_signal_action")`, `data.get("rsi_signal_started_at")`, `data.get("rsi_signal_last_seen_at")`, and `data.get("rsi_signal_candle")`**

```python
@dataclass(frozen=True)
class AutoTradeState:
    phase: str = "sell_1"
    last_completed_candle: str | None = None
    pending_order: PendingOrder | None = None
    emergency_confirmations: int = 0
    emergency_reason: str | None = None
    rsi_signal_action: str | None = None
    rsi_signal_started_at: str | None = None
    rsi_signal_last_seen_at: str | None = None
    rsi_signal_candle: str | None = None
```

- [ ] **Step 4: Run state tests and verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_auto_state.py -q`

Expected: all state tests pass.

- [ ] **Step 5: Add failing pure transition tests**

```python
def test_same_candidate_becomes_ready_only_after_thirty_seconds():
    state, ready = update_rsi_confirmation(AutoTradeState(), candidate_action="buy_1", candidate_candle="c1", now=utc(0))
    assert ready is None
    state, ready = update_rsi_confirmation(state, candidate_action="buy_1", candidate_candle="c1", now=utc(20))
    assert ready is None
    state, ready = update_rsi_confirmation(state, candidate_action="buy_1", candidate_candle="c1", now=utc(30))
    assert ready == "c1"


def test_loss_change_or_long_gap_restarts_confirmation():
    # None clears, a changed action starts at the new observation, and a 21-second gap restarts.


def test_same_action_can_continue_across_candle_boundary():
    # Start on c1, observe the same action on c2, and return ready with original candle c1.
```

- [ ] **Step 6: Run transition tests and verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_live_signal.py -q`

Expected: collection FAIL because `huntbot.live_signal` does not exist.

- [ ] **Step 7: Implement the pure transition**

```python
def update_rsi_confirmation(state, *, candidate_action, candidate_candle, now, hold_seconds=30, max_gap_seconds=20):
    if candidate_action is None or candidate_candle is None or candidate_candle == state.last_completed_candle:
        return clear_rsi_confirmation(state), None
    started = parse_optional_timestamp(state.rsi_signal_started_at)
    last_seen = parse_optional_timestamp(state.rsi_signal_last_seen_at)
    same = state.rsi_signal_action == candidate_action and started is not None and last_seen is not None
    if not same or (now - last_seen).total_seconds() > max_gap_seconds:
        return start_confirmation(state, candidate_action, candidate_candle, now), None
    observed = replace(state, rsi_signal_last_seen_at=now.isoformat())
    ready = state.rsi_signal_candle if (now - started).total_seconds() >= hold_seconds else None
    return observed, ready
```

Malformed timestamps are treated as absent and restart confirmation. `clear_rsi_confirmation` sets only the four confirmation fields to `None`.

- [ ] **Step 8: Run focused tests and commit Task 1**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_auto_state.py tests/test_live_signal.py -q`

Expected: all focused tests pass.

```bash
git add huntbot/auto_state.py huntbot/live_signal.py tests/test_auto_state.py tests/test_live_signal.py
git commit -m "feat: persist live RSI confirmation"
```

---

### Task 2: Integrate Provisional RSI Into The Auto Cycle

**Files:**
- Modify: `huntbot/auto_trader.py`
- Modify: `huntbot/config.py`
- Modify: `tests/test_auto_trader.py`

**Interfaces:**
- Consumes: `provisional_rsi`, `threshold_action`, and `five_minute_bucket` from `huntbot.intrabar_signals`.
- Consumes: Task 1 confirmation functions.
- Produces: `AutoCycleResult` with `status="confirming"`, no action, current price, provisional RSI, current risk diagnostics, and no order UUID while a valid action is younger than 30 seconds.

- [ ] **Step 1: Add failing cycle tests for 30-second maturity**

```python
def test_auto_cycle_confirms_provisional_rsi_for_thirty_seconds(tmp_path, monkeypatch):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    notifier = FakeNotifier()
    start = client.now
    monkeypatch.setattr("huntbot.auto_trader.provisional_rsi", lambda *args, **kwargs: 45.0)
    first = run_auto_cycle(client=client, notifier=notifier, state_path=path, live=False, now=start)
    second = run_auto_cycle(client=client, notifier=notifier, state_path=path, live=False, now=start + timedelta(seconds=20))
    mature = run_auto_cycle(client=client, notifier=notifier, state_path=path, live=False, now=start + timedelta(seconds=30))
    assert [first.status, second.status, mature.status] == ["confirming", "confirming", "dry_run"]
    assert mature.action == "buy_1"
    assert client.orders == []
```

Add separate tests proving stale orderbook data and first-candle emergency risk clear an existing confirmation, a 21-second observation gap restarts it, and a minimum-order failure consumes the signal candle.

- [ ] **Step 2: Run focused cycle tests and verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_auto_trader.py -k "provisional or confirmation or minimum" -q`

Expected: new tests fail because the cycle still evaluates only the latest completed candle.

- [ ] **Step 3: Add explicit timing constants**

```python
AUTO_RSI_HOLD_SECONDS = 30
AUTO_RSI_MAX_GAP_SECONDS = 20
```

- [ ] **Step 4: Replace completed-only normal RSI evaluation after emergency handling**

```python
completed = latest_completed_candle(five_minute_candles, unit=5, now=now)
completed_candles = [c for c in five_minute_candles if completed and c.timestamp <= completed.timestamp]
rsi_value = provisional_rsi(
    [c.close for c in completed_candles],
    current_price,
    period=RSI_PERIOD,
)
candidate_candle = five_minute_bucket(current_price_timestamp).isoformat()
candidate_action = threshold_action(
    state.phase,
    rsi_value,
    has_hunt=hunt_balance > 0,
    has_krw=krw_balance > 0,
)
state, ready_candle = update_rsi_confirmation(
    state,
    candidate_action=candidate_action,
    candidate_candle=candidate_candle,
    now=now,
    hold_seconds=AUTO_RSI_HOLD_SECONDS,
    max_gap_seconds=AUTO_RSI_MAX_GAP_SECONDS,
)
save_auto_state(state, state_path)
```

Return `confirming` when a candidate exists but is not ready. Return `waiting` when no candidate exists. Do not mark ordinary waiting candles as consumed.

- [ ] **Step 5: Preserve emergency and order safety**

Clear confirmation before every data-error, emergency-pending, emergency-confirmed, pending-order submission, and below-minimum return. For below minimum, also set `last_completed_candle=ready_candle`. Keep pending order reconciliation first and `emergency_halt` second.

- [ ] **Step 6: Run auto-trader tests and verify GREEN**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_auto_trader.py tests/test_auto_service.py -q`

Expected: all focused tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add huntbot/auto_trader.py huntbot/config.py tests/test_auto_trader.py
git commit -m "feat: trade after 30-second RSI confirmation"
```

---

### Task 3: Document, Verify, And Publish

**Files:**
- Modify: `README.md`
- Modify: `docs/aws-ec2-runbook.md`

**Interfaces:**
- Produces: operator-facing explanation and exact safe AWS update sequence.

- [ ] **Step 1: Update strategy documentation**

Replace the completed-candle normal RSI sentence with the provisional RSI 30-second rule, state that emergency protection remains completed-candle based, and explain the `confirming` status.

- [ ] **Step 2: Add the safe AWS update sequence**

```bash
sudo systemctl disable --now huntbot-auto
cd ~/huntbot-upload
git fetch origin
git checkout codex/upbit-rsi-sell-bot
git pull --ff-only origin codex/upbit-rsi-sell-bot
sudo cp -a /opt/huntbot/shared/data/state/auto-trading.json /opt/huntbot/shared/data/state/auto-trading.before-hold30s.json
sudo bash deploy/install-ubuntu.sh ~/huntbot-upload
sudo -u huntbot bash -lc 'cd /opt/huntbot/app && /opt/huntbot/venv/bin/python -m huntbot run-auto-5m --dry-run --once'
sudo systemctl enable --now huntbot-auto
sudo systemctl status huntbot-auto
```

- [ ] **Step 3: Run complete verification**

Run: `./.venv/Scripts/python.exe -m pytest -q`

Expected: all tests pass.

Run: `git diff --check`.

Expected: exit 0.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md docs/aws-ec2-runbook.md
git commit -m "docs: explain live 30-second RSI rollout"
```

- [ ] **Step 5: Push and create a draft pull request**

Verify `gh --version`, `gh auth status`, clean scope, branch, remote, and default branch. Push `codex/upbit-rsi-sell-bot` with tracking, then create a draft PR titled `[codex] use 30-second RSI confirmation for live trading`. The body must summarize strategy behavior, emergency priority, state migration, backtest evidence, AWS rollout, and the exact test count.
