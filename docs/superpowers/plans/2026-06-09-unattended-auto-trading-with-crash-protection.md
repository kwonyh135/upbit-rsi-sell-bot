# Unattended Auto-Trading With Crash Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a recoverable unattended KRW-HUNT auto-trading service with Telegram notifications, completed-candle RSI trading, and priority emergency crash liquidation.

**Architecture:** Keep the existing interactive trader intact and add a separate auto-trading runtime. Pure decision functions determine normal or emergency actions, an atomic JSON state records candle and pending-order progress, and an identifier-based Upbit order workflow reconciles ambiguous submissions before any new order. A 10-second service loop coordinates market data, account balances, Telegram notifications, logging, and Windows task operation.

**Tech Stack:** Python 3.12, requests, PyJWT, python-dotenv, pytest, Windows PowerShell Task Scheduler.

---

## File Map

- Create `huntbot/auto_state.py`: atomic runtime state persistence and pending-order models.
- Create `huntbot/risk.py`: pure crash-percentage and two-observation confirmation logic.
- Create `huntbot/notifier.py`: Telegram message delivery and notification formatting.
- Create `huntbot/auto_trader.py`: completed-candle selection, action decisions, order submission, reconciliation, and one-cycle orchestration.
- Create `huntbot/auto_service.py`: 10-second loop, retry/backoff, rotating logs, process lock, startup/shutdown notifications.
- Modify `huntbot/upbit_client.py`: order identifiers, order lookup, and configurable candle counts.
- Modify `huntbot/market_data.py`: latest-candle helpers and completed-candle selection support.
- Modify `huntbot/__main__.py`: `run-auto-5m --dry-run|--live` and `unlock-emergency`.
- Modify `huntbot/config.py`: emergency thresholds, loop interval, state/log paths.
- Modify `.env.example`: Telegram settings.
- Modify `README.md`: setup, safe activation, emergency halt, and Windows commands.
- Create `scripts/install-auto-task.ps1`: create/update the Windows scheduled task.
- Create `scripts/remove-auto-task.ps1`: disable and remove the scheduled task.
- Create tests for every new module and extend client/CLI tests.

### Task 1: Atomic Auto-Trading State

**Files:**
- Create: `huntbot/auto_state.py`
- Create: `tests/test_auto_state.py`

- [ ] **Step 1: Write failing state round-trip and atomic-write tests**

Test defaults, Decimal serialization, pending identifier/UUID fields, emergency count, `emergency_halt`, and replacement behavior without partial JSON.

- [ ] **Step 2: Run the focused test**

Run:

```powershell
& "C:\Users\김혜령\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest tests\test_auto_state.py -v
```

Expected: FAIL because `huntbot.auto_state` does not exist.

- [ ] **Step 3: Implement immutable state models and atomic save**

Define:

```python
@dataclass(frozen=True)
class PendingOrder:
    identifier: str
    action: str
    next_phase: str
    candle_timestamp: str | None
    rsi_value: float | None
    requested_amount: Decimal
    uuid: str | None = None

@dataclass(frozen=True)
class AutoTradeState:
    phase: str = "sell_1"
    last_completed_candle: str | None = None
    pending_order: PendingOrder | None = None
    emergency_confirmations: int = 0
    emergency_reason: str | None = None
```

Save through a sibling temporary file, flush and `os.fsync`, then `os.replace`.

- [ ] **Step 4: Re-run focused tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/auto_state.py tests/test_auto_state.py
git commit -m "feat: add atomic auto-trading state"
```

### Task 2: Emergency Crash Decision Logic

**Files:**
- Create: `huntbot/risk.py`
- Create: `tests/test_risk.py`
- Modify: `huntbot/config.py`

- [ ] **Step 1: Write failing threshold tests**

Cover:

- Five one-minute candles use their maximum `high`.
- Exactly 7% below the five-minute high triggers.
- Exactly 10% below average buy price triggers.
- Either trigger is sufficient.
- Two consecutive risky observations confirm emergency.
- A healthy observation resets the count.
- Missing, stale, or fewer than five candles returns a data error rather than a trade signal.
- `avg_buy_price <= 0` disables only the average-price condition.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_risk.py -v`; expect missing module/functions.

- [ ] **Step 3: Implement pure risk functions**

Use constants:

```python
EMERGENCY_HIGH_DROP_PCT = Decimal("7")
EMERGENCY_AVG_LOSS_PCT = Decimal("10")
EMERGENCY_CONFIRMATIONS = 2
AUTO_POLL_SECONDS = 10
```

Return a structured observation containing high-drop percent, average-loss percent, reason, risky flag, and updated confirmation count.

- [ ] **Step 4: Verify GREEN**

Run the focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/config.py huntbot/risk.py tests/test_risk.py
git commit -m "feat: detect confirmed HUNT price crashes"
```

### Task 3: Upbit Order Reconciliation API

**Files:**
- Modify: `huntbot/upbit_client.py`
- Modify: `tests/test_upbit_client.py`

- [ ] **Step 1: Write failing client tests**

Require:

```python
client.market_sell("KRW-HUNT", "100", identifier="huntbot-emergency-...")
client.market_buy("KRW-HUNT", "5000", identifier="huntbot-buy-...")
client.get_order(identifier="huntbot-buy-...")
client.get_order(uuid="...")
```

Verify JSON order bodies include `identifier` and authenticated query strings use exactly one lookup key.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_upbit_client.py -v`; expect signature/method failures.

- [ ] **Step 3: Implement identifier-aware methods**

Add optional identifiers to market orders and a `get_order` method calling authenticated `GET /v1/order`.

- [ ] **Step 4: Verify GREEN**

Run focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/upbit_client.py tests/test_upbit_client.py
git commit -m "feat: reconcile Upbit orders by identifier"
```

### Task 4: Market Data and Completed Five-Minute Candles

**Files:**
- Modify: `huntbot/market_data.py`
- Create: `tests/test_market_data.py`

- [ ] **Step 1: Write failing tests**

Cover latest one-minute candle parsing, exact `count=5`, newest trade price, stale candle rejection, and choosing the newest candle whose start plus five minutes is not later than `now`.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_market_data.py -v`.

- [ ] **Step 3: Implement latest-candle helpers**

Add helpers that do not sleep or paginate when only five candles are required, while retaining `fetch_recent_candles` for backtests.

- [ ] **Step 4: Verify GREEN**

Run focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/market_data.py tests/test_market_data.py
git commit -m "feat: select completed candles for auto trading"
```

### Task 5: Telegram Notifications

**Files:**
- Create: `huntbot/notifier.py`
- Create: `tests/test_notifier.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing notifier tests**

Test disabled notifier behavior, Telegram endpoint/body, startup message, submitted-order message, completed-order message, emergency message, error/recovery messages, and no token leakage.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_notifier.py -v`.

- [ ] **Step 3: Implement notifier**

Use `POST https://api.telegram.org/bot{token}/sendMessage` with `chat_id`, plain text, and a 10-second timeout. `TelegramNotifier.send()` raises `NotificationError` on transport or HTTP failure; the service catches and logs it without changing trading state.

- [ ] **Step 4: Verify GREEN**

Run focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add .env.example huntbot/notifier.py tests/test_notifier.py
git commit -m "feat: add Telegram trading notifications"
```

### Task 6: Pure Normal and Emergency Action Decisions

**Files:**
- Create: `huntbot/auto_trader.py`
- Create: `tests/test_auto_trader.py`

- [ ] **Step 1: Write failing decision tests**

Cover:

- `emergency_halt` always returns no order.
- Pending order always blocks another order.
- Confirmed emergency overrides every RSI phase.
- Emergency sell uses all available HUNT.
- `sell_1` uses half HUNT at RSI 60.
- `sell_2` uses all HUNT at RSI 65.
- `buy_1` uses half current KRW at RSI 45.
- `buy_2` uses maximum fee-safe current KRW at RSI 40.
- No normal signal is reprocessed for the same completed candle.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_auto_trader.py -v`.

- [ ] **Step 3: Implement decision types and pure selector**

Define an action carrying action name, side, amount/quantity, next phase, reason, candle timestamp, and RSI. Emergency actions have no candle dependency and always win.

- [ ] **Step 4: Verify GREEN**

Run focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/auto_trader.py tests/test_auto_trader.py
git commit -m "feat: decide unattended HUNT trades"
```

### Task 7: Durable Order Submission and Reconciliation

**Files:**
- Modify: `huntbot/auto_trader.py`
- Modify: `tests/test_auto_trader.py`

- [ ] **Step 1: Write failing workflow tests**

Test:

- Persist identifier before POST.
- Persist UUID after successful POST.
- Resolve `done` using UUID or identifier and then change phase.
- Sum trade `funds` and `volume` for actual notification values.
- Keep pending state for `wait`.
- Stop and retain pending state for `cancel` with partial execution.
- Recover after a simulated POST timeout by querying the pre-saved identifier.
- Never submit a second order while reconciliation is unresolved.
- Confirmed emergency transitions to `emergency_halt`.

- [ ] **Step 2: Verify RED**

Run the focused workflow tests.

- [ ] **Step 3: Implement submission and reconciliation**

Generate identifiers with phase/action plus UUID4. Treat state persistence as authoritative and notification as best-effort.

- [ ] **Step 4: Verify GREEN**

Run focused and full auto-trader tests.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/auto_trader.py tests/test_auto_trader.py
git commit -m "feat: make unattended orders recoverable"
```

### Task 8: One Auto-Trading Cycle

**Files:**
- Modify: `huntbot/auto_trader.py`
- Modify: `tests/test_auto_trader.py`

- [ ] **Step 1: Write failing cycle tests**

Use fake clients to verify the cycle:

- Loads balances including HUNT average buy price.
- Loads five 1-minute candles every cycle.
- Reconciles pending order before evaluating risk.
- Evaluates emergency risk before completed 5-minute RSI.
- Fetches enough 5-minute candles for RSI 14.
- Dry-run reports an action without order submission or phase mutation.
- Live mode submits through the durable workflow.
- Successful healthy cycle clears a prior error-recovery marker.

- [ ] **Step 2: Verify RED**

Run focused tests.

- [ ] **Step 3: Implement `run_auto_cycle`**

Inject clock, notifier, and client for deterministic tests. Return a structured cycle result for logging.

- [ ] **Step 4: Verify GREEN**

Run focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/auto_trader.py tests/test_auto_trader.py
git commit -m "feat: run one unattended trading cycle"
```

### Task 9: Continuous Service, Lock, Logging, and CLI

**Files:**
- Create: `huntbot/auto_service.py`
- Create: `tests/test_auto_service.py`
- Modify: `huntbot/__main__.py`
- Modify: `huntbot/config.py`

- [ ] **Step 1: Write failing service and parser tests**

Test required `--dry-run|--live`, dry-run-only `--once`, 10-second polling, bounded backoff, startup/shutdown notification, repeated-error rate limiting, single-process lock, and graceful keyboard interruption.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_auto_service.py -v`.

- [ ] **Step 3: Implement service**

Use `RotatingFileHandler`, a held Windows lock file, injected sleep for tests, and `run_auto_cycle`. Live mode is explicit; dry-run never calls order submission.

- [ ] **Step 4: Add `unlock-emergency`**

Require current phase `emergency_halt`, no pending order, and explicit local phrase `UNLOCK KRW-HUNT`; reset to `sell_1` without placing an order.

- [ ] **Step 5: Verify GREEN**

Run service tests and the full suite.

- [ ] **Step 6: Commit**

```powershell
git add huntbot/auto_service.py huntbot/__main__.py huntbot/config.py tests/test_auto_service.py
git commit -m "feat: add unattended auto-trading service"
```

### Task 10: Windows Task Scheduler Scripts

**Files:**
- Create: `scripts/install-auto-task.ps1`
- Create: `scripts/remove-auto-task.ps1`
- Create: `tests/test_windows_scripts.py`

- [ ] **Step 1: Write failing script-content tests**

Assert the install script uses the repository path, bundled Python, `run-auto-5m --live`, restart-on-failure settings, one-instance policy, log directory, and AC sleep guidance. Assert removal targets only the named HUNT bot task.

- [ ] **Step 2: Verify RED**

Run `pytest tests/test_windows_scripts.py -v`.

- [ ] **Step 3: Implement scripts**

Create or replace a task named `HuntBot-Auto-5m` at user logon. Do not execute the installer during tests or implementation verification.

- [ ] **Step 4: Verify GREEN**

Run focused tests.

- [ ] **Step 5: Commit**

```powershell
git add scripts/install-auto-task.ps1 scripts/remove-auto-task.ps1 tests/test_windows_scripts.py
git commit -m "feat: add Windows auto-start scripts"
```

### Task 11: Documentation and Safe Activation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-09-unattended-auto-trading-design.md`
- Modify: `docs/superpowers/specs/2026-06-09-unattended-auto-trading-design.html`

- [ ] **Step 1: Document Telegram and API permissions**

Include `.env` keys, Upbit View Orders permission for reconciliation, Order permission for live trading, and no Withdrawal permission.

- [ ] **Step 2: Document dry-run burn-in**

Provide exact bundled-Python commands for `run-auto-5m --dry-run`, log inspection, Telegram test, live activation, emergency halt inspection, and local unlock.

- [ ] **Step 3: Document Windows installation without executing it**

Show task installation and removal commands plus AC sleep settings.

- [ ] **Step 4: Validate HTML anchors and UTF-8**

Run the existing HTML parser validation and expect no missing anchors, duplicate IDs, or replacement characters.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/superpowers/specs/2026-06-09-unattended-auto-trading-design.md docs/superpowers/specs/2026-06-09-unattended-auto-trading-design.html
git commit -m "docs: explain unattended trading safety"
```

### Task 12: Final Verification Without Live Orders

**Files:**
- No production file changes expected.

- [ ] **Step 1: Run the full test suite**

```powershell
& "C:\Users\김혜령\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI help**

Verify `run-auto-5m` requires a mode and `unlock-emergency` is present.

- [ ] **Step 3: Run one networked dry-run cycle**

Run:

```powershell
& "C:\Users\김혜령\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m huntbot run-auto-5m --dry-run --once
```

Confirm phase, current price, crash percentages, completed candle, RSI, and intended action. The command must not call any order POST endpoint.

- [ ] **Step 4: Test Telegram with an explicit test-only command**

Send a startup/test notification only after the user has entered Telegram credentials and authorized the outbound message.

- [ ] **Step 5: Inspect git diff and state**

Confirm `.env`, `data/state`, logs, and API credentials are not staged. Do not install the scheduled task or start unattended live trading without a separate explicit user approval.
