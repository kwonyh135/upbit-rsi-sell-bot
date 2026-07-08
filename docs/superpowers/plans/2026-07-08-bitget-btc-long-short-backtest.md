# Bitget BTC Long/Short Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible six-month BTCUSDT perpetual-futures backtest that compares long-only, short-only, bidirectional, and regime-filtered RSI strategies and generates a standalone Korean HTML report.

**Architecture:** Add a public Bitget data client and BTC-specific research models without touching the Upbit live path. Feed validated five-minute candles and funding settlements through a look-ahead-free regime classifier and a target-exposure futures simulator, then aggregate development, holdout, stress, and regime results for Markdown, JSON, and standalone HTML outputs.

**Tech Stack:** Python 3.11+, standard library (`dataclasses`, `datetime`, `decimal`, `csv`, `json`, `html`), existing `requests`, existing RSI implementation, pytest.

## Global Constraints

- Market is Bitget `BTCUSDT` USDT-M perpetual futures.
- Use the latest six complete calendar months of completed five-minute candles plus warm-up data.
- Use one-way isolated 1x exposure and never hold long and short simultaneously.
- Base taker fee is 0.06%; base adverse slippage is 0.02%; stress slippage is 0.05% and 0.10%.
- Apply actual historical funding settlements with positive funding paid by longs and received by shorts.
- Signals use completed five-minute RSI 14 and execute at the next five-minute open.
- Development is the first four calendar months; holdout is the final two calendar months.
- Do not modify HUNT live trading, state, deployment, secrets, or AWS files.
- Use public Bitget endpoints only and never place an order.

## File Map

- Create `huntbot/bitget_public.py`: public HTTP client, date window, candle/funding download, CSV cache.
- Create `huntbot/btc_futures.py`: BTC futures models, regime classification, strategy state machine, accounting engine.
- Create `huntbot/btc_futures_study.py`: strategy matrix, segment runs, stress runs, recommendation rules, serialization payload.
- Create `huntbot/btc_futures_reporting.py`: Korean Markdown and standalone HTML rendering.
- Modify `huntbot/__main__.py`: add one research-only CLI command and output orchestration.
- Create `tests/test_bitget_public.py`, `tests/test_btc_futures.py`, `tests/test_btc_futures_study.py`, and `tests/test_btc_futures_reporting.py`.
- Generate `docs/bitget-btc-long-short-backtest-latest.md` and `docs/bitget-btc-long-short-backtest-latest.html` after downloading real data.

---

### Task 1: Public Bitget Data And Reproducible Cache

**Files:**
- Create: `huntbot/bitget_public.py`
- Create: `tests/test_bitget_public.py`

**Interfaces:**
- Produces: `FundingSettlement`, `complete_month_window()`, `BitgetPublicClient`, `download_history()`, `save_funding_snapshot()`, and `load_funding_snapshot()`.
- Reuses: `Candle`, `save_candle_snapshot()`, and `load_candle_snapshot()`.

- [ ] **Step 1: Write failing tests for month boundaries and API parsing**

```python
def test_complete_month_window_returns_six_full_months_and_warmup():
    warmup, start, end = complete_month_window(datetime(2026, 7, 8, tzinfo=timezone.utc))
    assert start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert warmup == datetime(2025, 11, 22, tzinfo=timezone.utc)

def test_parse_contract_candle_uses_utc_and_decimal():
    candle = parse_contract_candle(["1767225600000", "90000", "90100", "89900", "90050", "12.5", "1"])
    assert candle.market == "BTCUSDT"
    assert candle.unit == 5
    assert candle.close == Decimal("90050")
    assert candle.timestamp.tzinfo == timezone.utc

def test_parse_funding_settlement():
    item = parse_funding_settlement({"fundingRate": "0.0001", "fundingTime": "1767225600000"})
    assert item.rate == Decimal("0.0001")
```

- [ ] **Step 2: Run the tests and verify missing imports fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_bitget_public.py -q`

Expected: FAIL because `huntbot.bitget_public` does not exist.

- [ ] **Step 3: Implement models, UTC month arithmetic, and response parsers**

```python
@dataclass(frozen=True)
class FundingSettlement:
    timestamp: datetime
    rate: Decimal

def complete_month_window(now: datetime) -> tuple[datetime, datetime, datetime]:
    end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    start = _shift_months(end, -6)
    return start - timedelta(days=40), start, end

def parse_contract_candle(row: list[str]) -> Candle:
    return Candle(
        market="BTCUSDT", unit=5,
        timestamp=datetime.fromtimestamp(int(row[0]) / 1000, timezone.utc),
        open=Decimal(row[1]), high=Decimal(row[2]), low=Decimal(row[3]),
        close=Decimal(row[4]), volume=Decimal(row[5]),
    )
```

- [ ] **Step 4: Add paginated historical downloads and CSV round trips**

Use `GET /api/v2/mix/market/history-candles` with `symbol=BTCUSDT`, `productType=usdt-futures`, `granularity=5m`, `limit=200`, and backward-moving `endTime`. Use `GET /api/v2/mix/market/history-fund-rate` with pages of 100. Stop at the requested start boundary, deduplicate timestamps, and raise `RuntimeError` on non-`00000` responses or a pagination loop.

```python
class BitgetPublicClient:
    def __init__(self, session=requests, base_url="https://api.bitget.com"):
        self.session = session
        self.base_url = base_url

    def get_json(self, path: str, params: dict) -> dict:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "00000":
            raise RuntimeError(f"Bitget API error: {payload.get('code')} {payload.get('msg')}")
        return payload
```

- [ ] **Step 5: Run focused tests and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_bitget_public.py tests/test_market_data.py -q`

Expected: PASS.

```bash
git add huntbot/bitget_public.py tests/test_bitget_public.py
git commit -m "feat: add Bitget BTC futures data client"
```

### Task 2: Look-Ahead-Free Regime Classification

**Files:**
- Create: `huntbot/btc_futures.py`
- Create: `tests/test_btc_futures.py`

**Interfaces:**
- Produces: `Regime`, `classify_regimes(candles)`, `validate_candles(candles, start, end)`.
- Consumes: chronological five-minute `Candle` objects.

- [ ] **Step 1: Write failing validation and regime tests**

```python
def test_validate_candles_rejects_conflicting_duplicate():
    candles = [candle_at(0, close="100"), candle_at(0, close="101")]
    with pytest.raises(ValueError, match="conflicting duplicate"):
        validate_candles(candles, START, END)

def test_regime_is_not_visible_until_four_hour_bar_closes():
    candles = synthetic_trend_candles(four_hour_bars=205)
    regimes = classify_regimes(candles)
    boundary = candles[200 * 48].timestamp
    assert regimes[boundary - timedelta(minutes=5)] == Regime.NEUTRAL
    assert regimes[boundary] in {Regime.BULL, Regime.BEAR, Regime.NEUTRAL}
```

- [ ] **Step 2: Run and verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_btc_futures.py -q`

Expected: FAIL because regime functions do not exist.

- [ ] **Step 3: Implement candle validation and four-hour aggregation**

`validate_candles` must return sorted unique candles plus a missing-interval count. It must require every timestamp from the six-month test start through test end, while allowing warm-up gaps to be disclosed rather than counted as test failure.

Aggregate UTC-aligned four-hour bars and publish each completed bar's regime only to subsequent five-minute timestamps. Compute EMA as `alpha = 2 / (period + 1)` and seed with the first close; do not backfill early regime labels.

```python
class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"

def _label(close: Decimal, ema50: Decimal, ema200: Decimal) -> Regime:
    if close > ema200 and ema50 > ema200:
        return Regime.BULL
    if close < ema200 and ema50 < ema200:
        return Regime.BEAR
    return Regime.NEUTRAL
```

- [ ] **Step 4: Run focused tests and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_btc_futures.py -q`

Expected: PASS.

```bash
git add huntbot/btc_futures.py tests/test_btc_futures.py
git commit -m "feat: classify BTC futures market regimes"
```

### Task 3: 1x Long And Short Accounting Engine

**Files:**
- Modify: `huntbot/btc_futures.py`
- Modify: `tests/test_btc_futures.py`

**Interfaces:**
- Produces: `StrategyKind`, `FuturesConfig`, `FuturesTrade`, `PositionCycle`, `FuturesResult`, and `run_futures_backtest()`.
- Consumes: candles, funding settlements, regimes, and a test interval.

- [ ] **Step 1: Write failing tests for direction, split targets, and next-open fills**

```python
def test_long_profit_and_short_loss_have_opposite_signs():
    rising = candles_with_forced_rsi_and_next_opens([("enter", 100), ("exit", 110)])
    long_result = run_futures_backtest(rising, [], {}, config(StrategyKind.LONG_ONLY))
    short_result = run_futures_backtest(rising, [], {}, config(StrategyKind.SHORT_ONLY))
    assert long_result.gross_pnl > 0
    assert short_result.gross_pnl < 0

def test_signal_executes_at_next_open_with_adverse_slippage():
    result = run_fixture(signal_close=Decimal("100"), next_open=Decimal("102"), side="long")
    assert result.trades[0].market_price == Decimal("102")
    assert result.trades[0].execution_price == Decimal("102.0204")

def test_no_same_bar_reversal():
    result = run_reversal_fixture()
    assert result.trades[0].target_exposure == Decimal("0")
    assert result.trades[1].timestamp > result.trades[0].timestamp
```

- [ ] **Step 2: Write failing tests for fees, funding, and equity**

```python
def test_positive_funding_is_paid_by_long_and_received_by_short():
    settlement = FundingSettlement(T1, Decimal("0.001"))
    assert run_open_position("long", settlement).funding_pnl < 0
    assert run_open_position("short", settlement).funding_pnl > 0

def test_each_fill_charges_taker_fee_on_notional():
    result = run_single_fill(notional=Decimal("1500"), fee=Decimal("0.0006"))
    assert result.fee_cost == Decimal("0.9")
```

- [ ] **Step 3: Implement strategy target transitions**

Use target exposure values `-1`, `-0.5`, `0`, `0.5`, and `1`.

```python
def desired_target(kind, exposure, rsi_value, regime):
    allow_long = kind in {LONG_ONLY, BIDIRECTIONAL} and (not filtered(kind) or regime == Regime.BULL)
    allow_short = kind in {SHORT_ONLY, BIDIRECTIONAL} and (not filtered(kind) or regime == Regime.BEAR)
    if exposure > 0:
        if rsi_value >= 65: return Decimal("0")
        if rsi_value >= 60: return min(exposure, Decimal("0.5"))
        if rsi_value <= 40: return Decimal("1")
        return exposure
    if exposure < 0:
        if rsi_value <= 40: return Decimal("0")
        if rsi_value <= 45: return max(exposure, Decimal("-0.5"))
        if rsi_value >= 65: return Decimal("-1")
        return exposure
    if rsi_value <= 45 and allow_long: return Decimal("0.5")
    if rsi_value >= 60 and allow_short: return Decimal("-0.5")
    return Decimal("0")
```

Prevent direct sign changes: a requested opposite target becomes zero first, with the opposite entry allowed only after a later signal candle.

- [ ] **Step 4: Implement mark-to-market, execution, cycles, and metrics**

Use signed BTC quantity, cash collateral, and current equity. At each fill, trade the difference between current and target notional based on pre-fill equity. Apply adverse slippage upward for buys and downward for sells, then charge fee on absolute executed notional. Apply funding at settlement timestamps before the next price transition. Record an equity point for every test candle close.

Calculate return, annualized return, MDD, win rate, profit factor, average win/loss, time in market, turnover, direction contribution, costs, and cycle concentration. Force-close only for reporting at the final close and label that fill `end_of_test`.

- [ ] **Step 5: Run focused tests and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_btc_futures.py -q`

Expected: PASS, including exact Decimal accounting assertions.

```bash
git add huntbot/btc_futures.py tests/test_btc_futures.py
git commit -m "feat: simulate one-times BTC long and short strategies"
```

### Task 4: Development, Holdout, Stress, And Recommendation Study

**Files:**
- Create: `huntbot/btc_futures_study.py`
- Create: `tests/test_btc_futures_study.py`

**Interfaces:**
- Produces: `StudyRun`, `BtcFuturesStudy`, `run_btc_futures_study()`, `study_to_json()`.
- Consumes: the Task 3 simulator and the exact four-month/two-month calendar split.

- [ ] **Step 1: Write failing matrix and split tests**

```python
def test_study_runs_all_strategies_and_slippage_scenarios():
    study = run_btc_futures_study(candles, funding, START, END)
    assert len(study.full_runs) == 6 * 3
    assert {run.config.slippage for run in study.full_runs} == {
        Decimal("0.0002"), Decimal("0.0005"), Decimal("0.001")
    }

def test_holdout_starts_after_four_complete_months():
    study = run_btc_futures_study(candles, funding, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 7, 1, tzinfo=UTC))
    assert study.holdout_start == datetime(2026, 5, 1, tzinfo=UTC)
```

- [ ] **Step 2: Write failing recommendation tests**

Cover each instability rule: negative holdout, MDD above 20%, negative 0.05% stress return, fewer than ten holdout cycles, over-50% profit concentration, and buy-and-hold underperformance with comparable drawdown.

```python
def test_negative_holdout_is_not_recommended():
    assert classify_conclusion(result(holdout_return="-1")) == "not recommended"

def test_all_gates_pass_requires_paper_trading_not_live_trading():
    assert classify_conclusion(stable_profitable_result()) == "recommended for further paper trading"
```

- [ ] **Step 3: Implement the run matrix and regime attribution**

Run cash and perpetual buy-and-hold benchmarks plus long-only, short-only, unfiltered bidirectional, and regime-filtered bidirectional strategies. Run each over development, holdout, and full intervals at all three slippage rates. Attribute interval equity changes to the regime known at the start of each candle.

Evaluate only fixed `60/65/45/40` thresholds in the primary result. Keep the optional five-point sensitivity search out of this first implementation unless all primary runs finish and tests remain fast; this preserves the agreed fixed-rule answer and avoids unnecessary optimization.

- [ ] **Step 4: Serialize reproducible JSON and run tests**

```python
def study_to_json(study, metadata):
    return json.dumps(
        {"metadata": metadata, "study": asdict(study)},
        ensure_ascii=True, indent=2, default=_json_default,
    ) + "\n"
```

Run: `./.venv/Scripts/python.exe -m pytest tests/test_btc_futures_study.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add huntbot/btc_futures_study.py tests/test_btc_futures_study.py
git commit -m "feat: compare BTC futures strategy variants"
```

### Task 5: Korean Markdown And Standalone HTML Report

**Files:**
- Create: `huntbot/btc_futures_reporting.py`
- Create: `tests/test_btc_futures_reporting.py`

**Interfaces:**
- Produces: `render_btc_markdown(study, metadata)` and `render_btc_html(study, metadata)`.
- Consumes: `BtcFuturesStudy` and data-quality metadata.

- [ ] **Step 1: Write failing content and safety tests**

```python
def test_html_is_standalone_korean_and_contains_required_sections():
    html = render_btc_html(study_fixture(), metadata_fixture())
    assert "<!doctype html>" in html.lower()
    assert "상승장" in html and "하락장" in html and "검증 구간" in html
    assert "수수료" in html and "펀딩비" in html and "최대 낙폭" in html
    assert "https://cdn" not in html and "<script src=" not in html

def test_report_never_labels_result_as_ready_for_live_trading():
    html = render_btc_html(stable_study_fixture())
    assert "추가 모의투자 권장" in html
    assert "즉시 실거래 권장" not in html
```

- [ ] **Step 2: Run and verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_btc_futures_reporting.py -q`

Expected: FAIL because the reporting module does not exist.

- [ ] **Step 3: Implement compact tables and inline SVG charts**

Escape all text with `html.escape`. Render equity and drawdown series as inline SVG polylines with deterministic coordinates. Include:

- Korean executive conclusion and instability reasons.
- Exact UTC and Korea-time coverage.
- Missing interval and funding count disclosure.
- Assumptions and execution timing.
- Full, development, holdout, and stress result tables.
- Long/short and bull/bear/neutral contribution tables.
- Fee, slippage, and funding totals.
- Equity and drawdown charts for benchmarks and primary strategies.
- Limitations, including completed-candle-only signals and no live-order capability.

- [ ] **Step 4: Run report tests and commit**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_btc_futures_reporting.py -q`

Expected: PASS.

```bash
git add huntbot/btc_futures_reporting.py tests/test_btc_futures_reporting.py
git commit -m "feat: render BTC futures backtest reports"
```

### Task 6: CLI, Real Six-Month Run, And Visual Verification

**Files:**
- Modify: `huntbot/__main__.py`
- Modify: `README.md`
- Test: `tests/test_bitget_public.py`
- Generate: `docs/bitget-btc-long-short-backtest-latest.md`
- Generate: `docs/bitget-btc-long-short-backtest-latest.html`
- Generate ignored cache: `data/backtests/bitget-btcusdt-5m-latest.csv`
- Generate ignored cache: `data/backtests/bitget-btcusdt-funding-latest.csv`
- Generate ignored result: `data/backtests/bitget-btc-long-short-study-latest.json`

**Interfaces:**
- Produces command: `python -m huntbot backtest-bitget-btc --months 6`.
- Accepts optional `--candles` and `--funding` cache paths for offline reproduction.

- [ ] **Step 1: Write a failing parser/orchestration test**

```python
def test_parser_accepts_bitget_btc_research_command():
    args = build_parser().parse_args(["backtest-bitget-btc", "--months", "6"])
    assert args.command == "backtest-bitget-btc"
    assert args.months == 6
```

- [ ] **Step 2: Add the research-only command**

The command must download or load cache, validate exactly six complete months, run the study, and atomically write JSON, Markdown, and HTML via temporary sibling files followed by `Path.replace()`.

```python
btc = subparsers.add_parser("backtest-bitget-btc")
btc.add_argument("--months", type=int, choices=[6], default=6)
btc.add_argument("--candles")
btc.add_argument("--funding")
```

Print the resolved data interval, missing count, all output paths, and the research conclusion. Do not call `load_environment()` or construct an authenticated client.

- [ ] **Step 3: Run the complete automated suite before network work**

Run: `./.venv/Scripts/python.exe -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 4: Download official Bitget data and run the study**

Run: `./.venv/Scripts/python.exe -m huntbot backtest-bitget-btc --months 6`

Expected: six complete months plus warm-up are cached; JSON, Markdown, and HTML paths are printed. If Bitget's API cannot supply the complete interval, preserve the partial cache, report the exact missing range, and do not fabricate a result.

- [ ] **Step 5: Verify generated values and report integrity**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest -q
Select-String -Path docs/bitget-btc-long-short-backtest-latest.md -Pattern "Holdout|상승장|하락장|funding|MDD"
Select-String -Path docs/bitget-btc-long-short-backtest-latest.html -Pattern "<!doctype html>|추가 모의투자|즉시 실거래 권장"
```

Expected: tests PASS; required report sections are present; the forbidden immediate-live recommendation is absent.

- [ ] **Step 6: Open and visually inspect the HTML**

Open `docs/bitget-btc-long-short-backtest-latest.html` in the in-app browser. Check desktop readability, no horizontal overflow in the summary, legible chart labels, correct Korean text, and visible caveats. Fix rendering defects and rerun reporting tests.

- [ ] **Step 7: Review repository isolation and commit**

Run: `git diff --name-only HEAD~5..HEAD` and `git status --short`.

Expected: no files under `deploy/`, no HUNT live modules (`auto_service.py`, `auto_trader.py`, `risk.py`, `config.py`), no `.env`, and no runtime state files are changed.

```bash
git add huntbot/__main__.py README.md docs/bitget-btc-long-short-backtest-latest.md docs/bitget-btc-long-short-backtest-latest.html tests/test_bitget_public.py
git commit -m "feat: add Bitget BTC long-short research command"
```

### Task 7: Final Review And Evidence

**Files:**
- Review all files changed by Tasks 1-6.

**Interfaces:**
- Produces: final test evidence and a concise user-facing result summary.

- [ ] **Step 1: Run fresh verification**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest -q
git status --short
git log -7 --oneline
```

Expected: all tests PASS; only deliberate report artifacts, if any, remain; task commits are visible.

- [ ] **Step 2: Check financial invariants from the result JSON**

Verify programmatically that every run starts at 3,000 USDT, exposure remains within `[-1, 1]`, timestamps are chronological, development and holdout do not overlap, costs are finite, and ending equity reconciles to starting equity plus gross P&L minus fees minus slippage plus funding.

- [ ] **Step 3: Summarize without overstating results**

Report the winning strategy only if it passes the declared holdout and stress gates. Otherwise state `inconclusive` or `not recommended`, identify the failed gates, and link the local HTML report. Explicitly state that no HUNT bot, AWS service, or live Bitget code was changed.
