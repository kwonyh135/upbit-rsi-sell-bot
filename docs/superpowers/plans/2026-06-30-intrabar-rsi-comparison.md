# Intrabar RSI Timing Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a public-data-only backtest comparing completed five-minute RSI signals, immediate intrabar signals, and intrabar signals held for 30 seconds.

**Architecture:** Add a resumable second-candle data boundary, then feed one shared chronological event stream into three stateful timing simulations. Keep execution, crash protection, reporting, and CLI orchestration separate so the live trader remains unchanged and every timing mode receives identical market data and costs.

**Tech Stack:** Python 3.11+, standard library dataclasses/CSV/JSON, existing `requests`, existing RSI and crash-protection modules, pytest.

## Global Constraints

- Use public Upbit quotation endpoints only; never call an order endpoint.
- Study the latest available 90 days of KRW-HUNT second candles and record actual coverage.
- RSI period is 14 with production thresholds 45, 40, 60, and 65.
- Initial capital is KRW 3,000,000 with no HUNT.
- Base fee is 0.05%; base adverse slippage is 0.05%, with 0.30% and 1.00% stress runs.
- Current protection is 6% high-to-close drop or 12% average-price loss, confirmed by two consecutive completed five-minute candles.
- Signals use only data available at their timestamp and fills use the next observed trade.
- Do not modify the AWS live service or its runtime state.

---

### Task 1: Public Second-Candle Client And Resumable Snapshot

**Files:**
- Modify: `huntbot/upbit_client.py`
- Create: `huntbot/second_data.py`
- Modify: `tests/test_upbit_client.py`
- Create: `tests/test_second_data.py`

**Interfaces:**
- Produces: `UpbitClient.get_second_candles(market, *, count=200, to=None) -> list[dict]`
- Produces: `SecondCandle`, `load_second_snapshot`, `save_second_snapshot`, and `download_second_candles`
- Consumes: Upbit's public `/v1/candles/seconds` response.

- [ ] **Step 1: Add a failing public-endpoint test**

```python
def test_public_second_candles_use_cursor_without_auth_header():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="s" * 32, session=session)

    client.get_second_candles("KRW-HUNT", count=200, to="2026-06-30T00:00:00Z")

    method, url, params, headers, timeout = session.calls[0]
    assert method == "GET"
    assert url.endswith("/v1/candles/seconds")
    assert params == {"market": "KRW-HUNT", "count": 200, "to": "2026-06-30T00:00:00Z"}
    assert headers is None
```

- [ ] **Step 2: Run the endpoint test and verify RED**

Run: `python -m pytest tests/test_upbit_client.py::test_public_second_candles_use_cursor_without_auth_header -q`

Expected: FAIL with `AttributeError: 'UpbitClient' object has no attribute 'get_second_candles'`.

- [ ] **Step 3: Implement the public client method**

```python
def get_second_candles(
    self,
    market: str,
    *,
    count: int = 200,
    to: str | None = None,
) -> list[dict]:
    params = {"market": market, "count": count}
    if to:
        params["to"] = to
    response = self.session.get(
        f"{self.server_url}/v1/candles/seconds",
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    time.sleep(0.12)
    return response.json()
```

- [ ] **Step 4: Run the endpoint test and verify GREEN**

Run: `python -m pytest tests/test_upbit_client.py -q`

Expected: all Upbit client tests PASS.

- [ ] **Step 5: Add failing parsing, persistence, deduplication, and resume tests**

```python
def test_second_snapshot_round_trips_and_sorts(tmp_path):
    later = second("2026-06-30T00:00:02+00:00", "102")
    earlier = second("2026-06-30T00:00:01+00:00", "101")
    path = tmp_path / "seconds.csv"
    save_second_snapshot([later, earlier, later], path)
    assert load_second_snapshot(path) == [earlier, later]


def test_download_resumes_before_oldest_saved_timestamp(tmp_path):
    path = tmp_path / "seconds.csv"
    save_second_snapshot([second("2026-06-30T00:01:00+00:00", "100")], path)
    client = FakeSecondClient([[raw_second("2026-06-30T00:00:30", 99)]])

    result = download_second_candles(
        client,
        "KRW-HUNT",
        start=datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 6, 30, 0, 2, tzinfo=timezone.utc),
        snapshot_path=path,
        sleep=lambda _: None,
    )

    assert client.calls[0]["to"].startswith("2026-06-30T00:01:00")
    assert [item.timestamp.second for item in result] == [30, 0]
```

- [ ] **Step 6: Run the second-data tests and verify RED**

Run: `python -m pytest tests/test_second_data.py -q`

Expected: collection FAIL because `huntbot.second_data` does not exist.

- [ ] **Step 7: Implement the second-candle data boundary**

```python
@dataclass(frozen=True)
class SecondCandle:
    market: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def parse_second_candle(raw: dict) -> SecondCandle:
    timestamp = datetime.fromisoformat(raw["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
    return SecondCandle(
        market=raw["market"],
        timestamp=timestamp,
        open=Decimal(str(raw["opening_price"])),
        high=Decimal(str(raw["high_price"])),
        low=Decimal(str(raw["low_price"])),
        close=Decimal(str(raw["trade_price"])),
        volume=Decimal(str(raw["candle_acc_trade_volume"])),
    )


def download_second_candles(client, market, *, start, end, snapshot_path, sleep=time.sleep):
    saved = load_second_snapshot(snapshot_path) if snapshot_path.exists() else []
    unique = {item.timestamp: item for item in saved if start <= item.timestamp < end}
    cursor = min(unique) if unique else end
    while cursor > start:
        page = client.get_second_candles(market, count=200, to=cursor.isoformat())
        if not page:
            break
        parsed = [parse_second_candle(item) for item in page]
        for item in parsed:
            if start <= item.timestamp < end:
                unique[item.timestamp] = item
        next_cursor = min(item.timestamp for item in parsed)
        if next_cursor >= cursor:
            raise RuntimeError("second-candle cursor did not move backward")
        cursor = next_cursor
        save_second_snapshot(unique.values(), snapshot_path)
        sleep(0.12)
    return [unique[key] for key in sorted(unique)]
```

Implement CSV fields `market,timestamp,open,high,low,close,volume`; save through a temporary file followed by `Path.replace` so interrupted writes do not corrupt the checkpoint.

- [ ] **Step 8: Run focused and full data tests**

Run: `python -m pytest tests/test_second_data.py tests/test_upbit_client.py -q`

Expected: all focused tests PASS.

- [ ] **Step 9: Commit the data boundary**

```bash
git add huntbot/upbit_client.py huntbot/second_data.py tests/test_upbit_client.py tests/test_second_data.py
git commit -m "feat: add resumable Upbit second-candle download"
```

---

### Task 2: Five-Minute Aggregation And Timing Signals

**Files:**
- Create: `huntbot/intrabar_signals.py`
- Create: `tests/test_intrabar_signals.py`

**Interfaces:**
- Consumes: `SecondCandle` and existing `huntbot.indicators.rsi`.
- Produces: `FiveMinuteBar`, `TimingMode`, `TimedSignal`, `SignalTracker`, `aggregate_five_minute_bars`, `provisional_rsi`, and `observe_signal`.

- [ ] **Step 1: Add failing aggregation and provisional-RSI tests**

```python
def test_aggregate_uses_trade_seconds_and_utc_five_minute_bucket():
    seconds = [
        second("2026-06-30T00:00:10+00:00", "100", high="101", low="99", volume="2"),
        second("2026-06-30T00:04:59+00:00", "105", high="106", low="104", volume="3"),
    ]
    bars = aggregate_five_minute_bars(seconds)
    assert bars[0].timestamp == datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc)
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume) == (
        Decimal("100"), Decimal("106"), Decimal("99"), Decimal("105"), Decimal("5")
    )


def test_provisional_rsi_replaces_only_unfinished_close():
    closes = [Decimal(str(value)) for value in range(100, 115)]
    expected = rsi([float(value) for value in [*closes, Decimal("90")]], period=14)[-1]
    assert provisional_rsi(closes, Decimal("90"), period=14) == expected
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_intrabar_signals.py -q`

Expected: collection FAIL because `huntbot.intrabar_signals` does not exist.

- [ ] **Step 3: Implement aggregation and provisional RSI**

```python
class TimingMode(str, Enum):
    COMPLETED = "completed"
    IMMEDIATE = "immediate"
    HOLD_30S = "hold_30s"


def five_minute_bucket(timestamp: datetime) -> datetime:
    return timestamp.replace(minute=timestamp.minute - timestamp.minute % 5, second=0, microsecond=0)


def provisional_rsi(completed_closes: Sequence[Decimal], current_price: Decimal, *, period: int = 14) -> float | None:
    if len(completed_closes) < period:
        return None
    return rsi([float(value) for value in [*completed_closes, current_price]], period=period)[-1]
```

Aggregate only buckets containing trades, preserving chronological first open, maximum high, minimum low, chronological last close, and summed volume.

- [ ] **Step 4: Add failing immediate and 30-second state-machine tests**

```python
def test_immediate_signals_on_first_threshold_crossing():
    signal, tracker = observe_signal(
        mode=TimingMode.IMMEDIATE,
        timestamp=utc("2026-06-30T00:01:10"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.9,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=SignalTracker(),
    )
    assert signal.action == "buy_1"
    assert signal.timestamp == utc("2026-06-30T00:01:10")


def test_hold_requires_thirty_wall_clock_seconds_without_price_update():
    tracker = SignalTracker()
    signal, tracker = observe_signal(
        mode=TimingMode.HOLD_30S,
        timestamp=utc("2026-06-30T00:01:10"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=44.9,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )
    assert signal is None
    signal, tracker = mature_held_signal(tracker, utc("2026-06-30T00:01:40"))
    assert signal.action == "buy_1"


def test_hold_resets_when_condition_breaks_before_thirty_seconds():
    tracker = SignalTracker(active_action="buy_1", active_since=utc("2026-06-30T00:01:10"))
    signal, tracker = observe_signal(
        mode=TimingMode.HOLD_30S,
        timestamp=utc("2026-06-30T00:01:25"),
        candle_start=utc("2026-06-30T00:00:00"),
        rsi_value=45.1,
        phase="sell_1",
        has_hunt=False,
        has_krw=True,
        tracker=tracker,
    )
    assert signal is None
    assert tracker.active_action is None
```

- [ ] **Step 5: Run the timing tests and verify RED**

Run: `python -m pytest tests/test_intrabar_signals.py -k "immediate or hold" -q`

Expected: FAIL because the timing state machine is missing.

- [ ] **Step 6: Implement phase-aware timing state**

```python
@dataclass(frozen=True)
class TimedSignal:
    action: str
    timestamp: datetime
    candle_start: datetime
    rsi_value: float


@dataclass(frozen=True)
class SignalTracker:
    active_action: str | None = None
    active_since: datetime | None = None
    active_candle: datetime | None = None
    acted_candle: datetime | None = None


def threshold_action(phase, rsi_value, *, has_hunt, has_krw):
    if rsi_value is None:
        return None
    if rsi_value >= 65 and has_hunt:
        return "sell_2"
    if rsi_value >= 60 and has_hunt and phase != "sell_2":
        return "sell_1"
    if phase == "buy_2":
        return "buy_2" if rsi_value <= 40 and has_krw else None
    return "buy_1" if rsi_value <= 45 and has_krw else None
```

`observe_signal` emits immediately for `IMMEDIATE`, starts or maintains a hold for `HOLD_30S`, resets a hold when its action changes or disappears, and refuses a second normal signal from `acted_candle`. `mature_held_signal` emits at `active_since + 30 seconds` without inventing an execution price.

- [ ] **Step 7: Run all signal tests**

Run: `python -m pytest tests/test_intrabar_signals.py -q`

Expected: all signal tests PASS.

- [ ] **Step 8: Commit the timing engine**

```bash
git add huntbot/intrabar_signals.py tests/test_intrabar_signals.py
git commit -m "feat: model completed and intrabar RSI signals"
```

---

### Task 3: Event-Driven Portfolio Simulation

**Files:**
- Create: `huntbot/intrabar_backtest.py`
- Create: `tests/test_intrabar_backtest.py`

**Interfaces:**
- Consumes: second candles and timing signals from Tasks 1 and 2.
- Consumes: `ProtectionConfig` and fixed-threshold protection helpers from `huntbot.crash_backtest`.
- Produces: `TimingBacktestConfig`, `TimingTrade`, `TimingBacktestResult`, and `run_timing_backtest`.

- [ ] **Step 1: Add a failing next-trade execution test**

```python
def test_signal_fills_on_next_observed_trade_with_adverse_slippage():
    seconds = threshold_fixture(signal_price="100", next_price="102")
    result = run_timing_backtest(
        seconds,
        TimingBacktestConfig(mode=TimingMode.IMMEDIATE, fee_rate=D("0.0005"), slippage_rate=D("0.0005")),
    )
    trade = result.trades[0]
    assert trade.signal_price == D("100")
    assert trade.market_price == D("102")
    assert trade.execution_price == D("102") * D("1.0005")
    assert trade.timestamp > trade.signal_timestamp
```

- [ ] **Step 2: Run the execution test and verify RED**

Run: `python -m pytest tests/test_intrabar_backtest.py::test_signal_fills_on_next_observed_trade_with_adverse_slippage -q`

Expected: collection FAIL because `huntbot.intrabar_backtest` does not exist.

- [ ] **Step 3: Implement portfolio and fill models**

```python
@dataclass(frozen=True)
class TimingBacktestConfig:
    mode: TimingMode
    fee_rate: Decimal = Decimal("0.0005")
    slippage_rate: Decimal = Decimal("0.0005")
    initial_krw: Decimal = Decimal("3000000")
    protection: ProtectionConfig | None = None


def execution_price(price: Decimal, action: str, slippage: Decimal) -> Decimal:
    if action.startswith("sell") or action == "emergency_sell":
        return price * (Decimal("1") - slippage)
    return price * (Decimal("1") + slippage)
```

The event loop must execute an already-pending signal before evaluating a new signal at the same observed trade. Buying deducts the requested KRW including fee-safe sizing; selling adds proceeds net of fee. Persist phase transitions exactly as production.

- [ ] **Step 4: Add failing no-look-ahead and missing-trade hold tests**

```python
def test_completed_mode_cannot_fill_at_signal_candle_close():
    result = run_timing_backtest(completed_signal_fixture(), config(TimingMode.COMPLETED))
    assert result.trades[0].timestamp == utc("2026-06-30T00:05:07")
    assert result.trades[0].signal_timestamp == utc("2026-06-30T00:05:00")


def test_held_signal_matures_during_gap_but_fills_at_next_trade():
    result = run_timing_backtest(hold_gap_fixture(), config(TimingMode.HOLD_30S))
    assert result.trades[0].signal_timestamp == utc("2026-06-30T00:01:40")
    assert result.trades[0].timestamp == utc("2026-06-30T00:02:05")
```

- [ ] **Step 5: Run the behavior tests and verify RED**

Run: `python -m pytest tests/test_intrabar_backtest.py -k "look_ahead or gap" -q`

Expected: FAIL until pending execution and hold maturity are implemented.

- [ ] **Step 6: Complete the chronological simulation**

```python
def run_timing_backtest(seconds, config):
    state = PortfolioState(cash=config.initial_krw, quantity=Decimal("0"), phase="sell_1")
    pending = None
    tracker = SignalTracker()
    for tick in sorted(seconds, key=lambda item: item.timestamp):
        if pending is not None and tick.timestamp > pending.timestamp:
            state, trade = fill_signal(state, pending, tick, config)
            pending = None
        matured, tracker = mature_held_signal(tracker, tick.timestamp)
        if matured is not None and pending is None:
            pending = matured
        state, pending, tracker = observe_market_tick(state, pending, tracker, tick, config)
    return build_result(state, config)
```

Maintain completed five-minute closes separately from the unfinished bucket. Final valuation uses the last observed close. Track an equity point after every fill and five-minute close for maximum drawdown.

- [ ] **Step 7: Add failing false-signal and crash-protection tests**

```python
def test_intrabar_signal_is_false_when_close_no_longer_meets_its_threshold():
    result = run_timing_backtest(false_buy_fixture(), config(TimingMode.IMMEDIATE))
    assert result.false_intrabar_signals == 1


def test_same_completed_crash_rule_applies_to_every_timing_mode():
    results = [
        run_timing_backtest(crash_fixture(), protected_config(mode))
        for mode in TimingMode
    ]
    assert [item.emergency_exits for item in results] == [1, 1, 1]
    assert all(any(trade.action == "emergency_sell" for trade in item.trades) for item in results)
```

- [ ] **Step 8: Implement close-time classification and fixed protection**

At each completed five-minute bucket, classify previously executed intrabar signals against that bucket's completed RSI. Evaluate 6%/12%/two-candle protection from completed bars only. A confirmed emergency schedules `emergency_sell`; after its simulated fill, clear HUNT and reset to `sell_1` to model the approved immediate manual-unlock proxy.

- [ ] **Step 9: Run focused and full simulator tests**

Run: `python -m pytest tests/test_intrabar_backtest.py -q`

Expected: all simulator tests PASS.

- [ ] **Step 10: Commit the simulator**

```bash
git add huntbot/intrabar_backtest.py tests/test_intrabar_backtest.py
git commit -m "feat: simulate RSI timing with next-trade fills"
```

---

### Task 4: Study Matrix, Reporting, And CLI

**Files:**
- Create: `huntbot/intrabar_study.py`
- Create: `huntbot/intrabar_reporting.py`
- Modify: `huntbot/__main__.py`
- Create: `tests/test_intrabar_study.py`
- Create: `tests/test_intrabar_reporting.py`
- Modify: `tests/test_auto_service.py`

**Interfaces:**
- Consumes: `run_timing_backtest` and the second-candle snapshot boundary.
- Produces: `TimingStudyResult`, `run_timing_study`, `render_timing_study_markdown`, and `timing_study_to_json`.
- Produces CLI: `python -m huntbot backtest-intrabar-rsi [--snapshot PATH] [--days 90]`.

- [ ] **Step 1: Add a failing study-matrix test**

```python
def test_study_runs_three_modes_two_protection_states_and_three_slippages(monkeypatch):
    calls = []
    monkeypatch.setattr("huntbot.intrabar_study.run_timing_backtest", lambda candles, config: calls.append(config) or fake_result(config))
    study = run_timing_study(sample_seconds())
    assert len(calls) == 54
    assert {call.mode for call in calls} == set(TimingMode)
    assert {call.slippage_rate for call in calls} == {D("0.0005"), D("0.003"), D("0.01")}
    assert {call.protection is None for call in calls} == {True, False}
    assert study.primary[TimingMode.COMPLETED.value].mode == TimingMode.COMPLETED
```

- [ ] **Step 2: Run the study test and verify RED**

Run: `python -m pytest tests/test_intrabar_study.py -q`

Expected: collection FAIL because `huntbot.intrabar_study` does not exist.

- [ ] **Step 3: Implement the fixed study matrix and chronological split**

```python
SLIPPAGES = (Decimal("0.0005"), Decimal("0.003"), Decimal("0.01"))


@dataclass(frozen=True)
class TimingStudyResult:
    split_at: datetime
    runs: dict[str, dict[str, TimingBacktestResult]]
    recommendation: str
    recommendation_reason: str


def run_timing_study(seconds):
    split_at = seconds[0].timestamp + (seconds[-1].timestamp - seconds[0].timestamp) * 2 / 3
    datasets = {
        "full": seconds,
        "training": [item for item in seconds if item.timestamp < split_at],
        "holdout": [item for item in seconds if item.timestamp >= split_at],
    }
    runs = {segment: {} for segment in datasets}
    for segment, segment_seconds in datasets.items():
        for protected in (True, False):
            for slippage in SLIPPAGES:
                for mode in TimingMode:
                    config = study_config(mode, slippage, protected=protected)
                    key = f"{'protected' if protected else 'unprotected'}:{slippage}:{mode.value}"
                    runs[segment][key] = run_timing_backtest(segment_seconds, config)
    recommendation, reason = evaluate_recommendation(runs)
    return TimingStudyResult(split_at, runs, recommendation, reason)
```

Run separate full, first-two-thirds, and last-one-third simulations rather than slicing a full-period equity curve, so each segment starts from the same KRW 3,000,000 baseline.

- [ ] **Step 4: Add failing report recommendation tests**

```python
def test_report_marks_intrabar_inconclusive_when_edge_disappears_at_point_three_percent():
    study = study_fixture(immediate_holdout="12", completed_holdout="10", immediate_stress="8", completed_stress="9")
    report = render_timing_study_markdown(study, metadata_fixture())
    assert "Recommendation: **completed**" in report
    assert "advantage did not survive 0.30% slippage" in report


def test_json_is_ascii_and_contains_metadata():
    payload = timing_study_to_json(study_fixture(), metadata_fixture())
    assert '"market": "KRW-HUNT"' in payload
    payload.encode("ascii")
```

- [ ] **Step 5: Run report tests and verify RED**

Run: `python -m pytest tests/test_intrabar_reporting.py -q`

Expected: collection FAIL because `huntbot.intrabar_reporting` does not exist.

- [ ] **Step 6: Implement deterministic JSON and Markdown reporting**

The report must include coverage, missing-trade seconds, the 18 full-period runs, the corresponding 18 training and 18 holdout runs, false signals, fees, slippage, cycle concentration, event-level differences, and limitations. Recommend an intrabar mode only when holdout return beats completed mode, MDD is not higher by more than 2 percentage points, and the return advantage remains positive at 0.30% slippage; otherwise recommend completed mode and state the failed criterion.

- [ ] **Step 7: Add a failing CLI parser test**

```python
def test_intrabar_backtest_parser_accepts_snapshot_and_days():
    args = build_parser().parse_args([
        "backtest-intrabar-rsi",
        "--snapshot", "data/backtests/test-seconds.csv",
        "--days", "90",
    ])
    assert args.snapshot.endswith("test-seconds.csv")
    assert args.days == 90
```

- [ ] **Step 8: Run the parser test and verify RED**

Run: `python -m pytest tests/test_auto_service.py::test_intrabar_backtest_parser_accepts_snapshot_and_days -q`

Expected: parser exits with an invalid command error.

- [ ] **Step 9: Wire the CLI without touching live commands**

```python
intrabar = subparsers.add_parser("backtest-intrabar-rsi")
intrabar.add_argument("--snapshot")
intrabar.add_argument("--days", type=int, default=90)


def run_intrabar_rsi_command(*, snapshot: str | None, days: int) -> int:
    now = datetime.now(timezone.utc)
    snapshot_path = Path(snapshot or "data/backtests/krw-hunt-1s-latest.csv")
    if snapshot:
        seconds = load_second_snapshot(snapshot_path)
    else:
        seconds = download_second_candles(
            UpbitClient(), MARKET,
            start=now - timedelta(days=days), end=now,
            snapshot_path=snapshot_path,
        )
    study = run_timing_study(seconds)
    write_timing_outputs(study, seconds, now)
    return 0
```

Write JSON to `data/backtests/intrabar-rsi-study-latest.json` and Markdown to `docs/intrabar-rsi-comparison-latest.md`.

- [ ] **Step 10: Run focused and full tests**

Run: `python -m pytest tests/test_intrabar_study.py tests/test_intrabar_reporting.py tests/test_auto_service.py -q`

Expected: all focused tests PASS.

Run: `python -m pytest -q`

Expected: the entire suite passes with zero failures.

- [ ] **Step 11: Commit study orchestration**

```bash
git add huntbot/intrabar_study.py huntbot/intrabar_reporting.py huntbot/__main__.py tests/test_intrabar_study.py tests/test_intrabar_reporting.py tests/test_auto_service.py
git commit -m "feat: report three-way RSI timing study"
```

---

### Task 5: Download, Execute, Validate, And Publish Results

**Files:**
- Generate: `data/backtests/krw-hunt-1s-latest.csv`
- Generate: `data/backtests/intrabar-rsi-study-latest.json`
- Generate: `docs/intrabar-rsi-comparison-latest.md`

**Interfaces:**
- Consumes: `python -m huntbot backtest-intrabar-rsi`.
- Produces: the evidence and recommendation requested by the user.

- [ ] **Step 1: Confirm generated market data is ignored while reports remain reviewable**

Run: `git check-ignore data/backtests/krw-hunt-1s-latest.csv`

Expected: `.gitignore` matches through the existing `data/backtests/` rule; no file change is needed.

- [ ] **Step 2: Download or resume the public 90-day snapshot and run the study**

Run: `python -m huntbot backtest-intrabar-rsi --days 90`

Expected: periodic page/coverage progress, then paths for the snapshot, JSON result, and Markdown report. No API keys are required and no order endpoint is called.

- [ ] **Step 3: Validate snapshot ordering and coverage**

Run:

```bash
python -c "from pathlib import Path; from huntbot.second_data import load_second_snapshot; p=Path('data/backtests/krw-hunt-1s-latest.csv'); x=load_second_snapshot(p); print(len(x), x[0].timestamp, x[-1].timestamp, all(a.timestamp < b.timestamp for a,b in zip(x,x[1:])))"
```

Expected: a positive count, approximately 90 days between endpoints subject to API availability, and final value `True`.

- [ ] **Step 4: Inspect machine-readable matrix completeness**

Run:

```bash
python -c "import json; d=json.load(open('data/backtests/intrabar-rsi-study-latest.json')); print(d['metadata']); print(len(d['study']['runs']))"
```

Expected: metadata for KRW-HUNT and 18 full-period scenario runs, plus training and holdout results.

- [ ] **Step 5: Run fresh verification**

Run: `python -m pytest -q`

Expected: all tests PASS with zero failures.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 6: Review the recommendation against raw metrics**

Confirm that the Markdown winner matches the holdout return, MDD, 0.30% stress result, and concentration rule in JSON. If coverage is shorter than 60 days or any mode completes fewer than two full cycles, label the result inconclusive rather than selecting an intrabar winner.

- [ ] **Step 7: Commit the reproducible report**

```bash
git add docs/intrabar-rsi-comparison-latest.md
git commit -m "docs: report intrabar RSI timing comparison"
```
