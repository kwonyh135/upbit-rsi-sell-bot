# Intrabar RSI Performance Report

## Status

Implemented a bounded-memory Wilder RSI preview accumulator and changed the timing backtest to use constant-time preview and completed-close updates. The 90-day study was not run.

## RED

Command:

```text
.\.venv\Scripts\python.exe -m pytest tests\test_indicators.py tests\test_intrabar_backtest.py -q
```

Result: collection failed with `ImportError: cannot import name 'WilderRsiPreview' from 'huntbot.indicators'`. This was the expected failure because the streaming API did not exist.

## GREEN

Focused command:

```text
.\.venv\Scripts\python.exe -m pytest tests\test_indicators.py tests\test_intrabar_signals.py tests\test_intrabar_backtest.py -q
```

Result: `27 passed in 0.88s`.

Full command:

```text
.\.venv\Scripts\python.exe -m pytest -q
```

Result: `182 passed in 3.72s`.

## Performance Evidence

A bounded benchmark used 5,000 completed closes and 1,000 candidate previews for both implementations. The values were exactly equal, including existing 6-decimal rounding.

```text
legacy_seconds=8.424140
incremental_seconds=0.001941
speedup=4340.1x
equal=True
state_fields=7
history_containers=0
```

The legacy path performs approximately 5,001 close conversions/iterations per preview, or about 5,001,000 history operations in this benchmark. The incremental path performs one candidate delta and one Wilder smoothing calculation per preview. Completed state contains seven scalar fields and no history container.

## Tests Added

- Streaming previews match `provisional_rsi` at every warmup point, including the initial period boundary.
- Three previews per completed point match the legacy helper over a 500-close mixed up/down sequence.
- Preview does not mutate completed state after 10,000 appends, and state retains no sequence or mapping.
- The timing simulator has no imported `provisional_rsi`, and a patched legacy helper that raises is never called.

## Files

- `huntbot/indicators.py`
- `huntbot/intrabar_backtest.py`
- `tests/test_indicators.py`
- `tests/test_intrabar_backtest.py`
- `.superpowers/sdd/performance-report.md`

## Self-Review

- Wilder initialization uses the first 14 changes exactly as `rsi` does; later updates use the same float operation order and 6-decimal helper.
- `preview` is read-only; `append` is the only completed-state mutation.
- At a five-minute rollover, the closing bar is previewed before it is appended. The new tick is previewed after that append, preserving no-look-ahead and former signal ordering.
- The legacy `provisional_rsi` remains unchanged as an oracle and for compatibility outside this simulator.
- Scope is limited to the RSI performance fix, its tests, and this report. No unrelated changes were present or modified.

## Concerns

None identified. `completed_bars` remains intentionally retained for protection-window behavior and is unrelated to the removed RSI history scan.
