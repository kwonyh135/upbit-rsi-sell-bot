# Local Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only localhost dashboard for live bot status, trade history, and performance.

**Architecture:** A separate Streamlit process synchronizes read-only Upbit data into a dashboard-only SQLite database. Pure collector, storage, and metric modules keep API behavior and financial calculations independently testable.

**Tech Stack:** Python 3.11+, SQLite, Streamlit, pandas, Altair, psutil, pytest

---

### Task 1: Upbit Read APIs

**Files:**
- Modify: `huntbot/upbit_client.py`
- Modify: `tests/test_upbit_client.py`

- [ ] Add failing tests for closed-order listing and query authentication.
- [ ] Run the focused tests and confirm the missing-method failure.
- [ ] Implement `get_closed_orders` using `GET /v1/orders/closed`.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Dashboard Storage

**Files:**
- Create: `huntbot/dashboard_store.py`
- Create: `tests/test_dashboard_store.py`

- [ ] Add failing tests for schema creation, UUID upsert, and snapshot fallback.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement the SQLite store with parameterized queries and transactions.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Collection And Health

**Files:**
- Create: `huntbot/dashboard_collector.py`
- Create: `tests/test_dashboard_collector.py`

- [ ] Add failing tests for action parsing, `cancel` fills, seven-day windows,
  stale fallback, log heartbeat, and read-only API usage.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement order, account, candle, state, log, and process collection.
- [ ] Run the focused tests and confirm they pass.

### Task 4: Performance Metrics

**Files:**
- Create: `huntbot/dashboard_metrics.py`
- Create: `tests/test_dashboard_metrics.py`

- [ ] Add failing tests for fees, moving-average realized P&L, partial
  inventory, unrealized P&L, return, equity curves, and drawdown gating.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement Decimal-based metric calculations.
- [ ] Run the focused tests and confirm they pass.

### Task 5: Streamlit UI

**Files:**
- Create: `huntbot/dashboard_app.py`
- Create: `.streamlit/config.toml`
- Create: `scripts/start-dashboard.ps1`
- Modify: `pyproject.toml`

- [ ] Add smoke tests for import safety and localhost launcher arguments.
- [ ] Run the focused tests and confirm failure.
- [ ] Build the Korean status, history, summary, and chart views.
- [ ] Add 15-second refresh, CSV download, stale/error states, and responsive
  styling without write controls.
- [ ] Run the focused tests and confirm they pass.

### Task 6: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] Document installation, launch URL, data rules, and operational safety.
- [ ] Run the complete pytest suite.
- [ ] Start Streamlit on `127.0.0.1` and verify desktop and mobile layouts in
  the in-app browser.
- [ ] Inspect git diff for secrets and unintended state/log changes.
- [ ] Commit the dashboard changes and push the existing PR branch.
