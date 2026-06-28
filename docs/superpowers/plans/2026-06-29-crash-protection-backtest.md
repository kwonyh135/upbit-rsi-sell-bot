# Crash Protection Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a reproducible six-month KRW-HUNT five-minute study comparing fixed, ATR-adaptive, and staged crash protection with manual and automatic recovery.

**Architecture:** Keep research code isolated from live trading in `huntbot/crash_backtest.py`. Reuse the public Upbit candle client, persist an ignored CSV snapshot, and expose one read-only CLI command that writes JSON and Markdown reports. Model completed-candle signals as next-open fills and reproduce the production RSI phase behavior.

**Tech Stack:** Python 3.11+, standard-library dataclasses/CSV/JSON, existing requests client, pytest.

## Global Constraints

- Do not modify live order placement or AWS service behavior.
- Do not read private API credentials or call an order endpoint.
- Use RSI 60/65 sells and 45/40 buys with production phase semantics.
- Use 0.05% fees and 0.05% normal slippage; stress crash exits at 0.30% and 1.00% slippage.
- Rank only close-confirmed results; low-touch results are sensitivity evidence.
- Use the first four months for shortlisting and the final two months for validation.

---

### Task 1: Reproducible Candle Snapshot

**Files:**
- Modify: `.gitignore`
- Modify: `huntbot/market_data.py`
- Create: `tests/test_crash_backtest.py`

**Interfaces:**
- Produces: `save_candle_snapshot(candles: list[Candle], path: Path) -> None`
- Produces: `load_candle_snapshot(path: Path) -> list[Candle]`
- Produces: `latest_complete_candles(candles: list[Candle], now: datetime, days: int = 183) -> list[Candle]`

- [ ] Write tests proving CSV round-trip preserves Decimal OHLCV and timezone-aware timestamps, and proving partial/future candles and candles older than 183 days are excluded.
- [ ] Run `python -m pytest tests/test_crash_backtest.py -v` and confirm failure because the interfaces do not exist.
- [ ] Implement the three interfaces with `csv.DictWriter`, `csv.DictReader`, and a completed-candle cutoff of `timestamp + unit <= now`.
- [ ] Add `data/backtests/` to `.gitignore`.
- [ ] Re-run `python -m pytest tests/test_crash_backtest.py -v` and confirm the tests pass.

### Task 2: Production-Faithful Portfolio Simulator

**Files:**
- Create: `huntbot/crash_backtest.py`
- Modify: `tests/test_crash_backtest.py`

**Interfaces:**
- Produces: immutable `ProtectionConfig`, `RecoveryConfig`, `CrashEvent`, and `CrashBacktestResult` dataclasses.
- Produces: `run_crash_backtest(candles, protection, recovery, fee_rate, normal_slippage_rate, crash_slippage_rate) -> CrashBacktestResult`.

- [ ] Add tests showing a signal from candle N fills at candle N+1 open; RSI 65 can sell all regardless of phase; `buy_2` cannot repeat `buy_1` at RSI 41-45; and fees/slippage lower final value.
- [ ] Run the focused tests and confirm they fail because the simulator is absent.
- [ ] Implement EMA20, ATR14, next-open pending actions, weighted average price, production RSI phase transitions, equity snapshots, MDD, and return-to-drawdown ratio.
- [ ] Re-run focused tests and the existing `tests/test_backtest.py` tests.

### Task 3: Three Protection Families and Recovery

**Files:**
- Modify: `huntbot/crash_backtest.py`
- Modify: `tests/test_crash_backtest.py`

**Interfaces:**
- Produces: `fixed_candidates()`, `adaptive_candidates()`, and `staged_candidates()` iterators.
- Produces: `recovery_candidates()` containing manual 6/24/72-hour and automatic 1/3/6-hour variants.
- Produces: `run_crash_study(candles: list[Candle]) -> CrashStudyResult`.

- [ ] Add tests for consecutive fixed-threshold confirmation, ATR widening, staged 50% then full exits, manual cooldown, automatic healthy-streak plus EMA20/RSI gating, and permanent-halt reference behavior.
- [ ] Run focused tests and confirm each new behavior fails before implementation.
- [ ] Implement bounded candidate grids and make protection suppress normal RSI orders while warning/halt state is active.
- [ ] Implement chronological four-month/two-month splitting, train shortlisting, validation evaluation, false-exit counting, cash-time and recovery-duration metrics.
- [ ] Rank candidates with validation return at least 90% of no-protection validation return by lowest MDD and then return-to-drawdown ratio; retain best-per-family and adjacent-parameter/stress evidence.
- [ ] Re-run `python -m pytest tests/test_crash_backtest.py -v`.

### Task 4: Read-Only CLI and Reports

**Files:**
- Modify: `huntbot/__main__.py`
- Create: `huntbot/crash_reporting.py`
- Modify: `tests/test_crash_backtest.py`
- Create at runtime: `docs/crash-protection-backtest-latest.md`
- Create at runtime: `data/backtests/krw-hunt-5m-latest.csv`
- Create at runtime: `data/backtests/crash-study-latest.json`

**Interfaces:**
- Produces: CLI `python -m huntbot backtest-crash-5m [--snapshot PATH]`.
- Produces: `render_crash_study_markdown(study, metadata) -> str` and `study_to_json(study, metadata) -> str`.

- [ ] Add tests proving the parser accepts the command and reports include candle range, baseline, three family winners, recovery mode, return, MDD, emergency exits, and limitations.
- [ ] Run focused tests and confirm failure before implementation.
- [ ] Implement the read-only command: reuse a supplied snapshot or fetch 264 public pages, filter to completed recent candles, save the snapshot, run the study, and write both reports.
- [ ] Run all tests with `python -m pytest`.

### Task 5: Execute Current Study and Review Evidence

**Files:**
- Update at runtime: `docs/crash-protection-backtest-latest.md`

- [ ] Run `python -m huntbot backtest-crash-5m` with network access and capture the exact first/last candle timestamps and count.
- [ ] Confirm the last candle is no older than one completed five-minute interval at download time.
- [ ] Inspect family winners, baseline, validation eligibility, stress slippage, and low-touch sensitivity for contradictions or implausible behavior.
- [ ] Run `python -m pytest` again after the generated report exists.
- [ ] Review `git diff --check`, `git status --short`, and the final Markdown report before making any recommendation.
