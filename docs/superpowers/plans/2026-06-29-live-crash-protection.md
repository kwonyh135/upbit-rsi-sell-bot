# Live Completed-Candle Crash Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the live HUNT bot to liquidate after two consecutive risky completed five-minute candles using 6% high-to-close or 12% average-loss thresholds, with immediate existing manual unlock and no cooldown.

**Architecture:** Add a pure completed-candle risk evaluator in `huntbot/risk.py`, then make `run_auto_cycle` use it before normal RSI selection while reusing the same five-minute candle fetch. Preserve the existing pending-order and manual unlock workflow. Align the research simulator's confirmation streak with real timestamp adjacency and report the exact user-selected rule separately from optimized candidates.

**Tech Stack:** Python 3.11+, Decimal, existing Upbit client, pytest.

## Global Constraints

- Emergency thresholds are exactly 6% same-candle high-to-close and 12% average-buy-price-to-close.
- Confirmation requires two risky completed five-minute candles exactly five minutes apart.
- One risky candle blocks every normal RSI order but places no emergency order.
- Confirmed risk sells all available HUNT and enters `emergency_halt` after reconciliation.
- Keep immediate local `unlock-emergency`; add no timer, automatic unlock, or Telegram unlock.
- Do not change RSI 60/65 sell and 45/40 buy behavior.

---

### Task 1: Completed Five-Minute Candle Risk Evaluator

**Files:**
- Modify: `huntbot/config.py`
- Modify: `huntbot/risk.py`
- Modify: `tests/test_risk.py`

**Interfaces:**
- Produces: `evaluate_completed_candle_crash_risk(five_minute_candles, average_buy_price, now) -> CrashRiskResult`.
- Preserves: `CrashRiskResult` fields consumed by `run_auto_cycle` and dashboard logging.

- [ ] Add failing boundary tests where 6.00% high drop and 5.00% average loss are risky, values immediately below are healthy, and only candles with `timestamp + 5 minutes <= now` are eligible.
- [ ] Add failing sequence tests where two adjacent risky candles confirm, one risky candle reports one confirmation, a healthy latest candle resets to zero, and a timestamp gap prevents confirmation.
- [ ] Run `python -m pytest tests/test_risk.py -v` and confirm failures are caused by the missing evaluator and old thresholds.
- [ ] Set `EMERGENCY_HIGH_DROP_PCT = Decimal("6")` and `EMERGENCY_AVG_LOSS_PCT = Decimal("5")`, then implement the pure evaluator using Decimal percentage drops and exact five-minute adjacency.
- [ ] Re-run `python -m pytest tests/test_risk.py -v` and commit the passing evaluator.

### Task 2: Live Auto-Cycle Integration and Halt Idempotence

**Files:**
- Modify: `huntbot/auto_trader.py`
- Modify: `tests/test_auto_trader.py`

**Interfaces:**
- Consumes: `evaluate_completed_candle_crash_risk(...)` from Task 1.
- Preserves: `run_auto_cycle(...) -> AutoCycleResult` and existing order reconciliation.

- [ ] Add failing cycle tests proving the first risky completed candle returns `emergency_pending`, two adjacent risky completed candles select one full `emergency_sell`, a gap does not confirm, and repeated polling of the same candles does not increment beyond their derived result.
- [ ] Add a failing test proving a persisted `emergency_halt` cycle returns `halted` without sending an emergency message or calling an order endpoint.
- [ ] Run focused tests and confirm failures against the current one-minute/orderbook risk behavior.
- [ ] Fetch five-minute candles once, evaluate completed-candle risk, persist the derived confirmation/reason, and reuse those candles for RSI. Keep the orderbook only for current price and minimum-order checks.
- [ ] Return immediately for `emergency_halt` after pending reconciliation so notifications and liquidation cannot repeat.
- [ ] Re-run `tests/test_auto_trader.py`, `tests/test_auto_service.py`, and `tests/test_risk.py`; commit the live integration.

### Task 3: Timestamp-Adjacent Backtest and Exact User Rule

**Files:**
- Modify: `huntbot/crash_backtest.py`
- Modify: `huntbot/crash_reporting.py`
- Modify: `tests/test_crash_backtest.py`

**Interfaces:**
- Produces: fixed/adaptive streaks that reset when consecutive candle timestamps differ by more than `candle.unit` minutes.
- Adds exact live-rule results to `CrashStudyResult`: immediate-unlock proxy, permanent-halt reference, 0.30% stress, and 1.00% stress.

- [ ] Add a failing simulator test where two risky records separated by ten minutes do not trigger an emergency, while five-minute-adjacent records do.
- [ ] Add failing report assertions for a dedicated `User-selected live rule (6% / 12% / 2 candles)` section and its immediate/permanent/stress results.
- [ ] Run focused tests and verify the new expectations fail.
- [ ] Reset simulator risk streaks on non-adjacent timestamps and evaluate `ProtectionConfig(fixed, window=1, high=6, loss=5, confirmations=2)` with manual-immediate and permanent recovery.
- [ ] Render the exact rule separately and state that it was user-selected, not the prior optimized winner.
- [ ] Re-run `tests/test_crash_backtest.py` and commit the aligned research behavior.

### Task 4: Fresh Study, Documentation, and Release Verification

**Files:**
- Modify: `README.md`
- Update at runtime: `docs/crash-protection-backtest-latest.md`

- [ ] Document the live 6%/12%/two-completed-candle rule and immediate manual unlock command.
- [ ] Run `python -m huntbot backtest-crash-5m` to refresh public data and regenerate the exact-rule report.
- [ ] Inspect exact-rule return, MDD, emergency exits, stress results, validation events, and candle freshness before recommending deployment.
- [ ] Run `python -m pytest -p no:cacheprovider --basetemp=.pytest-run-live-crash-final` and confirm all tests pass.
- [ ] Run `git diff --check`, commit the documentation/report, push `codex/upbit-rsi-sell-bot`, and update draft PR #5.
