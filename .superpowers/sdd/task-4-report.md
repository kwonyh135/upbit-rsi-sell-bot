# Task 4 Report: Study Matrix, Reporting, And CLI

Status: Complete.

## RED / GREEN

- RED study: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_study.py -q` -> collection error, `ModuleNotFoundError: No module named 'huntbot.intrabar_study'`.
- GREEN study: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_study.py -q` -> `1 passed in 0.06s`.
- RED reporting: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_reporting.py -q` -> collection error, `ModuleNotFoundError: No module named 'huntbot.intrabar_reporting'`.
- GREEN reporting: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_reporting.py -q` -> `3 passed in 0.09s`.
- RED CLI parser: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_auto_service.py::test_intrabar_backtest_parser_accepts_snapshot_and_days -q` -> parser rejected `backtest-intrabar-rsi` as an invalid command.
- RED CLI orchestration: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_auto_service.py::test_intrabar_snapshot_command_writes_json_and_markdown -q` -> `AttributeError` because `huntbot.__main__.run_timing_study` was absent.
- GREEN CLI: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_auto_service.py -k "intrabar" -q` -> `2 passed, 10 deselected in 0.53s`.

## Tests

- Focused: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_study.py tests/test_intrabar_reporting.py tests/test_auto_service.py -q` -> `16 passed in 0.67s`.
- Full suite: `& '.\.venv\Scripts\python.exe' -m pytest -q` -> `170 passed in 2.47s`.
- Whitespace: `git diff --check` -> no whitespace errors (Git emitted only existing LF-to-CRLF working-copy warnings).

## Files

- `huntbot/intrabar_study.py`
- `huntbot/intrabar_reporting.py`
- `huntbot/__main__.py`
- `tests/test_intrabar_study.py`
- `tests/test_intrabar_reporting.py`
- `tests/test_auto_service.py`

## Self-Review

- Confirmed 54 independent simulator calls: 18 each for full, training, and holdout, with every config initialized at KRW 3,000,000.
- Confirmed the protected study preset is the approved 6% high-drop / 12% average-loss / two-completed-candle rule.
- Confirmed recommendation checks holdout return, MDD within 2 percentage points, and positive advantage at 0.30% slippage.
- Confirmed deterministic ASCII JSON and Markdown coverage for all 54 runs, costs, false signals, concentration, event differences, and limitations.
- Confirmed snapshot mode performs no download and writes the required JSON and Markdown paths.
- Confirmed the existing live parser and `run-auto-5m` dispatch behavior were not changed.

## Concerns

- Missing-trade seconds intentionally count UTC wall-clock seconds without an observed trade; they do not imply missing exchange records.
- Cycle concentration is descriptive (busiest UTC day share) and is not an additional Task 4 recommendation gate.
- The real 90-day download and generated study artifacts remain Task 5 work.

## Review Fixes (2026-07-01)

### RED / GREEN

- RED: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_study.py tests/test_intrabar_reporting.py tests/test_auto_service.py -q` -> `5 failed, 19 passed in 1.02s`; failures covered the one-bar protected preset, eligible-candidate fallback, under-60-day gating, fewer-than-two-cycle gating, and deterministic cycle reporting.
- GREEN: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_study.py tests/test_intrabar_reporting.py tests/test_auto_service.py -q` -> `24 passed in 0.79s`.

### Tests

- Focused: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_intrabar_study.py tests/test_intrabar_reporting.py tests/test_auto_service.py -q` -> `24 passed in 0.79s`.
- Full suite: `& '.\.venv\Scripts\python.exe' -m pytest -q` -> `178 passed in 2.59s`.

### Self-Review

- Confirmed the protected preset exactly uses one high-window bar, 6% high drop, 12% average loss, and two confirmations.
- Confirmed immediate and hold-30s eligibility are evaluated independently, then the highest-return eligible holdout candidate is selected.
- Confirmed Markdown and JSON both suppress a timing winner below 60 actual coverage days or when any protected/base-slippage full-period mode has fewer than two deterministic buy/sell cycles.
- Confirmed completed cycles are derived in chronological trade order and emitted for every primary mode.
- Confirmed the chronological boundary assigns timestamps before the split to training and timestamps at/after it to holdout using independent lists, while preserving 54 simulator calls.
- Confirmed CLI defaults use 90 days, the latest one-second snapshot path, a public `UpbitClient` downloader call, and exact `end - start == 90 days`; the existing live parser was unchanged.

### Concerns

- A completed cycle is counted when chronological trades have observed at least one buy action and at least one sell or emergency-sell action; staged actions within the same side do not independently complete a cycle.
