# Upbit RSI HUNT Sell Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that backtests RSI 14 overheat sell conditions for `KRW-HUNT`, lets the user select one condition, and safely executes dry-run or confirmed live market sells for half of the actual Upbit HUNT balance.

**Architecture:** The bot is a small Python package named `huntbot`. Pure calculation modules cover RSI, strategy state, and backtesting; Upbit HTTP access is isolated in one client; the CLI composes those modules and defaults to dry-run behavior.

**Tech Stack:** Python 3.11+, `requests`, `PyJWT`, `python-dotenv`, `pytest`, standard-library `argparse`, `json`, `decimal`, and `dataclasses`.

---

## File Structure

- Create `.gitignore`: exclude `.env`, cache files, local state, logs, and Python build artifacts.
- Create `.env.example`: document required Upbit env vars without real secrets.
- Create `pyproject.toml`: package metadata and test dependencies.
- Create `README.md`: user setup and command guide.
- Create `huntbot/__init__.py`: package marker.
- Create `huntbot/__main__.py`: CLI entrypoint.
- Create `huntbot/config.py`: constants, env loading, config paths.
- Create `huntbot/models.py`: shared dataclasses for candles, strategies, balances, and results.
- Create `huntbot/indicators.py`: RSI calculation.
- Create `huntbot/strategy.py`: overheat/reset decision logic.
- Create `huntbot/backtest.py`: simulated 3,000,000 KRW HUNT sell strategy.
- Create `huntbot/upbit_client.py`: public and authenticated Upbit API requests.
- Create `huntbot/market_data.py`: candle pagination and cache.
- Create `huntbot/state.py`: selected strategy and live cycle state persistence.
- Create `huntbot/trader.py`: dry-run/live sell orchestration.
- Create `tests/test_indicators.py`: RSI tests.
- Create `tests/test_strategy.py`: re-entry and stop-sell tests.
- Create `tests/test_backtest.py`: simulation tests.
- Create `tests/test_upbit_client.py`: mocked request/signing behavior tests.
- Create `tests/test_trader.py`: dry-run/live safety tests.

## User Secret Setup

The user must create `.env` after `.env.example` exists:

```dotenv
UPBIT_OPEN_API_ACCESS_KEY=put_access_key_here
UPBIT_OPEN_API_SECRET_KEY=put_secret_key_here
UPBIT_OPEN_API_SERVER_URL=https://api.upbit.com
```

The user must not paste real keys into chat, docs, source files, screenshots, or logs.

## Task 1: Project Skeleton And Secret Safety

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `huntbot/__init__.py`
- Create: `huntbot/__main__.py`

- [ ] **Step 1: Write project metadata and ignored files**

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
dist/
build/
*.egg-info/
data/cache/
data/state/
logs/
```

Create `.env.example`:

```dotenv
UPBIT_OPEN_API_ACCESS_KEY=put_access_key_here
UPBIT_OPEN_API_SECRET_KEY=put_secret_key_here
UPBIT_OPEN_API_SERVER_URL=https://api.upbit.com
```

Create `pyproject.toml`:

```toml
[project]
name = "huntbot"
version = "0.1.0"
description = "KRW-HUNT RSI overheat sell bot for Upbit"
requires-python = ">=3.11"
dependencies = [
  "PyJWT>=2.8",
  "python-dotenv>=1.0",
  "requests>=2.31",
]

[project.optional-dependencies]
test = [
  "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Add initial README**

Create `README.md` with:

```markdown
# HUNT RSI Sell Bot

This bot backtests RSI 14 overheat sell thresholds for `KRW-HUNT` and can sell half of the actual Upbit HUNT balance after explicit live confirmation.

## Safety

- Do not enable withdrawal permission on the Upbit API key.
- Do not commit `.env`.
- Default trading mode is dry-run.
- Live market sell requires `--live` and the exact phrase `SELL KRW-HUNT`.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Edit `.env` locally and paste your real Upbit keys there.

## Commands

```powershell
python -m huntbot backtest
python -m huntbot select --unit 60 --sell-rsi 75 --reset-rsi 68
python -m huntbot watch --dry-run
python -m huntbot watch --live
```
```

- [ ] **Step 3: Add a placeholder CLI that lists commands**

Create `huntbot/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `huntbot/__main__.py`:

```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huntbot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backtest")

    select = subparsers.add_parser("select")
    select.add_argument("--unit", type=int, required=True)
    select.add_argument("--sell-rsi", type=float, required=True)
    select.add_argument("--reset-rsi", type=float, required=True)

    watch = subparsers.add_parser("watch")
    mode = watch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    watch.add_argument("--loop", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    print(f"Command not implemented yet: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify skeleton**

Run:

```powershell
python -m huntbot backtest
```

Expected:

```text
Command not implemented yet: backtest
```

- [ ] **Step 5: Commit**

```powershell
git add .gitignore .env.example pyproject.toml README.md huntbot
git commit -m "chore: scaffold huntbot project"
```

## Task 2: Models And RSI Indicator

**Files:**
- Create: `huntbot/models.py`
- Create: `huntbot/indicators.py`
- Create: `tests/test_indicators.py`

- [ ] **Step 1: Write failing RSI tests**

Create `tests/test_indicators.py`:

```python
from huntbot.indicators import rsi


def test_rsi_returns_none_until_period_is_available():
    values = rsi([100, 101, 102, 103, 104], period=14)
    assert values == [None, None, None, None, None]


def test_rsi_handles_flat_prices_as_neutral():
    values = rsi([100] * 20, period=14)
    assert values[14] == 50.0
    assert values[-1] == 50.0


def test_rsi_returns_high_value_for_consistent_gains():
    values = rsi([100 + index for index in range(20)], period=14)
    assert values[-1] == 100.0
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_indicators.py -v
```

Expected: FAIL because `huntbot.indicators` does not exist.

- [ ] **Step 3: Add dataclasses and RSI implementation**

Create `huntbot/models.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Candle:
    market: str
    unit: int
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class StrategyConfig:
    market: str
    unit: int
    rsi_period: int
    sell_rsi: float
    reset_rsi: float


@dataclass(frozen=True)
class BacktestResult:
    unit: int
    sell_rsi: float
    reset_rsi: float
    final_return_pct: float
    final_total_value: Decimal
    sell_count: int
    remaining_quantity: Decimal
    cash: Decimal
    max_drawdown_pct: float
```

Create `huntbot/indicators.py`:

```python
def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(closes) < period + 1:
        return [None] * len(closes)

    values: list[float | None] = [None] * len(closes)
    gains: list[float] = []
    losses: list[float] = []

    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    values[period] = _rsi_from_averages(avg_gain, avg_loss)

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        values[index] = _rsi_from_averages(avg_gain, avg_loss)

    return values


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return round(100 - (100 / (1 + relative_strength)), 6)
```

- [ ] **Step 4: Run RSI tests**

Run:

```powershell
pytest tests/test_indicators.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/models.py huntbot/indicators.py tests/test_indicators.py
git commit -m "feat: add RSI calculation"
```

## Task 3: Strategy State Decisions

**Files:**
- Create: `huntbot/strategy.py`
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write failing strategy tests**

Create `tests/test_strategy.py`:

```python
from decimal import Decimal

from huntbot.strategy import CycleState, evaluate_sell_signal


def test_first_overheat_signal_sells_when_value_is_large_enough():
    decision = evaluate_sell_signal(
        rsi_value=75.0,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("3000000"),
        available_quantity=Decimal("1000"),
        cycle=CycleState(ready=True),
    )
    assert decision.should_sell is True
    assert decision.sell_quantity == Decimal("500")
    assert decision.next_cycle.ready is False


def test_repeated_overheat_does_not_sell_before_reset():
    decision = evaluate_sell_signal(
        rsi_value=78.0,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("2000000"),
        available_quantity=Decimal("500"),
        cycle=CycleState(ready=False),
    )
    assert decision.should_sell is False
    assert decision.next_cycle.ready is False


def test_reset_below_threshold_allows_next_sell_later():
    reset_decision = evaluate_sell_signal(
        rsi_value=67.9,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("2000000"),
        available_quantity=Decimal("500"),
        cycle=CycleState(ready=False),
    )
    assert reset_decision.should_sell is False
    assert reset_decision.next_cycle.ready is True


def test_value_below_500000_blocks_sell():
    decision = evaluate_sell_signal(
        rsi_value=80.0,
        sell_rsi=75.0,
        reset_rsi=68.0,
        holding_value=Decimal("499999"),
        available_quantity=Decimal("100"),
        cycle=CycleState(ready=True),
    )
    assert decision.should_sell is False
    assert decision.reason == "holding_value_below_minimum"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_strategy.py -v
```

Expected: FAIL because `huntbot.strategy` does not exist.

- [ ] **Step 3: Implement strategy decisions**

Create `huntbot/strategy.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


MIN_HOLDING_VALUE_KRW = Decimal("500000")


@dataclass(frozen=True)
class CycleState:
    ready: bool = True


@dataclass(frozen=True)
class SellDecision:
    should_sell: bool
    sell_quantity: Decimal
    reason: str
    next_cycle: CycleState


def evaluate_sell_signal(
    *,
    rsi_value: float | None,
    sell_rsi: float,
    reset_rsi: float,
    holding_value: Decimal,
    available_quantity: Decimal,
    cycle: CycleState,
) -> SellDecision:
    if rsi_value is None:
        return SellDecision(False, Decimal("0"), "rsi_unavailable", cycle)
    if holding_value < MIN_HOLDING_VALUE_KRW:
        return SellDecision(False, Decimal("0"), "holding_value_below_minimum", cycle)
    if rsi_value < reset_rsi:
        return SellDecision(False, Decimal("0"), "reset_ready", CycleState(ready=True))
    if rsi_value >= sell_rsi and cycle.ready:
        return SellDecision(True, available_quantity / Decimal("2"), "sell_signal", CycleState(ready=False))
    if rsi_value >= sell_rsi:
        return SellDecision(False, Decimal("0"), "already_sold_this_cycle", cycle)
    return SellDecision(False, Decimal("0"), "waiting", cycle)
```

- [ ] **Step 4: Run strategy tests**

Run:

```powershell
pytest tests/test_strategy.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/strategy.py tests/test_strategy.py
git commit -m "feat: add RSI sell signal logic"
```

## Task 4: Backtest Engine

**Files:**
- Create: `huntbot/backtest.py`
- Create: `tests/test_backtest.py`

- [ ] **Step 1: Write failing backtest tests**

Create `tests/test_backtest.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

from huntbot.backtest import run_backtest
from huntbot.models import Candle


def candle(index: int, close: str) -> Candle:
    price = Decimal(close)
    return Candle(
        market="KRW-HUNT",
        unit=60,
        timestamp=datetime(2026, 1, 1, index % 24, tzinfo=timezone.utc),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1000"),
    )


def test_backtest_starts_with_3000000_krw_value():
    candles = [candle(i, str(100 + i)) for i in range(30)]
    result = run_backtest(candles, sell_rsi=70.0, reset_rsi=60.0, initial_krw=Decimal("3000000"))
    assert result.final_total_value > Decimal("0")
    assert result.unit == 60


def test_backtest_records_half_sell_when_rsi_overheats():
    closes = [100] * 15 + [110, 120, 130, 140, 150, 145, 140, 135, 130, 125, 140, 155, 170]
    candles = [candle(i, str(close)) for i, close in enumerate(closes)]
    result = run_backtest(candles, sell_rsi=70.0, reset_rsi=60.0, initial_krw=Decimal("3000000"))
    assert result.sell_count >= 1
    assert result.cash > Decimal("0")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_backtest.py -v
```

Expected: FAIL because `huntbot.backtest` does not exist.

- [ ] **Step 3: Implement backtest engine**

Create `huntbot/backtest.py`:

```python
from decimal import Decimal

from huntbot.indicators import rsi
from huntbot.models import BacktestResult, Candle
from huntbot.strategy import CycleState, evaluate_sell_signal


def run_backtest(
    candles: list[Candle],
    *,
    sell_rsi: float,
    reset_rsi: float,
    initial_krw: Decimal = Decimal("3000000"),
) -> BacktestResult:
    if len(candles) < 15:
        raise ValueError("at least 15 candles are required")

    first_price = candles[0].close
    quantity = initial_krw / first_price
    cash = Decimal("0")
    peak_value = initial_krw
    max_drawdown_pct = 0.0
    sell_count = 0
    cycle = CycleState(ready=True)
    rsi_values = rsi([float(candle.close) for candle in candles], period=14)

    for candle, rsi_value in zip(candles, rsi_values):
        holding_value = quantity * candle.close
        total_value = cash + holding_value
        if total_value > peak_value:
            peak_value = total_value
        drawdown = float((peak_value - total_value) / peak_value * Decimal("100"))
        max_drawdown_pct = max(max_drawdown_pct, drawdown)

        decision = evaluate_sell_signal(
            rsi_value=rsi_value,
            sell_rsi=sell_rsi,
            reset_rsi=reset_rsi,
            holding_value=holding_value,
            available_quantity=quantity,
            cycle=cycle,
        )
        cycle = decision.next_cycle
        if decision.should_sell:
            sell_quantity = decision.sell_quantity
            cash += sell_quantity * candle.close
            quantity -= sell_quantity
            sell_count += 1

    final_price = candles[-1].close
    final_total_value = cash + (quantity * final_price)
    final_return_pct = float((final_total_value - initial_krw) / initial_krw * Decimal("100"))

    return BacktestResult(
        unit=candles[0].unit,
        sell_rsi=sell_rsi,
        reset_rsi=reset_rsi,
        final_return_pct=round(final_return_pct, 6),
        final_total_value=final_total_value,
        sell_count=sell_count,
        remaining_quantity=quantity,
        cash=cash,
        max_drawdown_pct=round(max_drawdown_pct, 6),
    )


def run_candidate_search(candles_by_unit: dict[int, list[Candle]]) -> list[BacktestResult]:
    results: list[BacktestResult] = []
    reset_deltas = [3, 5, 7, 10, 15]
    for unit, candles in candles_by_unit.items():
        for sell_rsi in range(65, 91):
            for delta in reset_deltas:
                reset_rsi = float(sell_rsi - delta)
                results.append(run_backtest(candles, sell_rsi=float(sell_rsi), reset_rsi=reset_rsi))
    return sorted(results, key=lambda item: item.final_return_pct, reverse=True)
```

- [ ] **Step 4: Run backtest tests**

Run:

```powershell
pytest tests/test_backtest.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add huntbot/backtest.py tests/test_backtest.py
git commit -m "feat: add RSI backtest engine"
```

## Task 5: Upbit Client And Market Data

**Files:**
- Create: `huntbot/config.py`
- Create: `huntbot/upbit_client.py`
- Create: `huntbot/market_data.py`
- Create: `tests/test_upbit_client.py`

- [ ] **Step 1: Write mocked client tests**

Create `tests/test_upbit_client.py`:

```python
from huntbot.upbit_client import UpbitClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "response text"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.text)


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers, timeout))
        return FakeResponse([])

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers, timeout))
        return FakeResponse({"uuid": "order-1"})


def test_public_candles_do_not_include_auth_header():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="secret", session=session)
    client.get_minute_candles("KRW-HUNT", unit=60, count=2)
    method, url, params, headers, timeout = session.calls[0]
    assert method == "GET"
    assert url.endswith("/v1/candles/minutes/60")
    assert params["market"] == "KRW-HUNT"
    assert headers is None


def test_market_sell_uses_ask_market_volume():
    session = FakeSession()
    client = UpbitClient(access_key="access", secret_key="secret", session=session)
    client.market_sell("KRW-HUNT", "123.45")
    method, url, body, headers, timeout = session.calls[0]
    assert method == "POST"
    assert body == {"market": "KRW-HUNT", "side": "ask", "ord_type": "market", "volume": "123.45"}
    assert headers["Authorization"].startswith("Bearer ")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_upbit_client.py -v
```

Expected: FAIL because `huntbot.upbit_client` does not exist.

- [ ] **Step 3: Implement config and Upbit client**

Create `huntbot/config.py`:

```python
from pathlib import Path

from dotenv import load_dotenv


MARKET = "KRW-HUNT"
RSI_PERIOD = 14
INITIAL_BACKTEST_KRW = 3_000_000
MIN_HOLDING_VALUE_KRW = 500_000
DEFAULT_SERVER_URL = "https://api.upbit.com"
DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"
STATE_DIR = DATA_DIR / "state"


def load_environment() -> None:
    load_dotenv()
```

Create `huntbot/upbit_client.py`:

```python
import hashlib
import os
import time
import uuid
from urllib.parse import urlencode

import jwt
import requests

from huntbot.config import DEFAULT_SERVER_URL


class UpbitClient:
    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        server_url: str | None = None,
        session=None,
    ) -> None:
        self.access_key = access_key or os.environ.get("UPBIT_OPEN_API_ACCESS_KEY", "")
        self.secret_key = secret_key or os.environ.get("UPBIT_OPEN_API_SECRET_KEY", "")
        self.server_url = (server_url or os.environ.get("UPBIT_OPEN_API_SERVER_URL") or DEFAULT_SERVER_URL).rstrip("/")
        self.session = session or requests.Session()

    def get_minute_candles(self, market: str, *, unit: int, count: int = 200, to: str | None = None) -> list[dict]:
        params = {"market": market, "count": count}
        if to:
            params["to"] = to
        response = self.session.get(
            f"{self.server_url}/v1/candles/minutes/{unit}",
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        time.sleep(0.12)
        return response.json()

    def get_accounts(self) -> list[dict]:
        response = self.session.get(
            f"{self.server_url}/v1/accounts",
            headers=self._auth_headers({}),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_order_chance(self, market: str) -> dict:
        params = {"market": market}
        response = self.session.get(
            f"{self.server_url}/v1/orders/chance",
            params=params,
            headers=self._auth_headers(params),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def market_sell(self, market: str, volume: str) -> dict:
        body = {"market": market, "side": "ask", "ord_type": "market", "volume": volume}
        response = self.session.post(
            f"{self.server_url}/v1/orders",
            json=body,
            headers=self._auth_headers(body),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self, params: dict) -> dict[str, str]:
        if not self.access_key or not self.secret_key:
            raise RuntimeError("Upbit API keys are missing. Create .env from .env.example.")
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if params:
            query = urlencode(params).encode()
            payload["query_hash"] = hashlib.sha512(query).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self.secret_key)
        return {"Authorization": f"Bearer {token}", "accept": "application/json"}
```

- [ ] **Step 4: Implement market data normalization**

Create `huntbot/market_data.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

from huntbot.models import Candle
from huntbot.upbit_client import UpbitClient


def parse_candle(raw: dict, *, unit: int) -> Candle:
    timestamp = datetime.fromisoformat(raw["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
    return Candle(
        market=raw["market"],
        unit=unit,
        timestamp=timestamp,
        open=Decimal(str(raw["opening_price"])),
        high=Decimal(str(raw["high_price"])),
        low=Decimal(str(raw["low_price"])),
        close=Decimal(str(raw["trade_price"])),
        volume=Decimal(str(raw["candle_acc_trade_volume"])),
    )


def fetch_recent_candles(client: UpbitClient, market: str, *, unit: int, pages: int) -> list[Candle]:
    candles: list[Candle] = []
    to: str | None = None
    for _ in range(pages):
        raw_page = client.get_minute_candles(market, unit=unit, count=200, to=to)
        if not raw_page:
            break
        candles.extend(parse_candle(item, unit=unit) for item in raw_page)
        oldest = min(item["candle_date_time_utc"] for item in raw_page)
        to = oldest
    unique = {candle.timestamp: candle for candle in candles}
    return [unique[key] for key in sorted(unique)]
```

- [ ] **Step 5: Run client tests**

Run:

```powershell
pytest tests/test_upbit_client.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add huntbot/config.py huntbot/upbit_client.py huntbot/market_data.py tests/test_upbit_client.py
git commit -m "feat: add Upbit API client"
```

## Task 6: State, CLI Backtest, And Strategy Selection

**Files:**
- Create: `huntbot/state.py`
- Modify: `huntbot/__main__.py`

- [ ] **Step 1: Implement local state persistence**

Create `huntbot/state.py`:

```python
import json
from dataclasses import asdict
from pathlib import Path

from huntbot.config import STATE_DIR
from huntbot.models import StrategyConfig
from huntbot.strategy import CycleState


STRATEGY_PATH = STATE_DIR / "strategy.json"
CYCLE_PATH = STATE_DIR / "cycle.json"


def save_strategy(strategy: StrategyConfig, path: Path = STRATEGY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(strategy), indent=2), encoding="utf-8")


def load_strategy(path: Path = STRATEGY_PATH) -> StrategyConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return StrategyConfig(**data)


def save_cycle(cycle: CycleState, path: Path = CYCLE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cycle), indent=2), encoding="utf-8")


def load_cycle(path: Path = CYCLE_PATH) -> CycleState:
    if not path.exists():
        return CycleState(ready=True)
    data = json.loads(path.read_text(encoding="utf-8"))
    return CycleState(**data)
```

- [ ] **Step 2: Wire backtest and select CLI**

Replace `huntbot/__main__.py` with:

```python
import argparse
from decimal import Decimal

from huntbot.backtest import run_candidate_search
from huntbot.config import MARKET, RSI_PERIOD, load_environment
from huntbot.market_data import fetch_recent_candles
from huntbot.models import StrategyConfig
from huntbot.state import save_strategy
from huntbot.upbit_client import UpbitClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huntbot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backtest")

    select = subparsers.add_parser("select")
    select.add_argument("--unit", type=int, choices=[5, 15, 60], required=True)
    select.add_argument("--sell-rsi", type=float, required=True)
    select.add_argument("--reset-rsi", type=float, required=True)

    watch = subparsers.add_parser("watch")
    mode = watch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    watch.add_argument("--loop", action="store_true")
    return parser


def main() -> int:
    load_environment()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "backtest":
        return run_backtest_command()
    if args.command == "select":
        strategy = StrategyConfig(
            market=MARKET,
            unit=args.unit,
            rsi_period=RSI_PERIOD,
            sell_rsi=args.sell_rsi,
            reset_rsi=args.reset_rsi,
        )
        save_strategy(strategy)
        print(f"Saved strategy: unit={args.unit}, sell_rsi={args.sell_rsi}, reset_rsi={args.reset_rsi}")
        return 0
    print("watch command will be implemented in the trader task")
    return 0


def run_backtest_command() -> int:
    client = UpbitClient()
    pages_by_unit = {60: 22, 15: 88, 5: 264}
    candles_by_unit = {
        unit: fetch_recent_candles(client, MARKET, unit=unit, pages=pages)
        for unit, pages in pages_by_unit.items()
    }
    results = run_candidate_search(candles_by_unit)
    print("unit sell_rsi reset_rsi return_pct final_value sells cash remaining_hunt max_dd")
    for result in results[:20]:
        print(
            f"{result.unit} {result.sell_rsi:.1f} {result.reset_rsi:.1f} "
            f"{result.final_return_pct:.2f} {result.final_total_value.quantize(Decimal('1'))} "
            f"{result.sell_count} {result.cash.quantize(Decimal('1'))} "
            f"{result.remaining_quantity:.8f} {result.max_drawdown_pct:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run backtest command manually**

Run:

```powershell
python -m huntbot backtest
```

Expected: prints the top 20 candidate rows. If network is blocked, rerun with approved network access.

- [ ] **Step 4: Run select command**

Run:

```powershell
python -m huntbot select --unit 60 --sell-rsi 75 --reset-rsi 68
```

Expected:

```text
Saved strategy: unit=60, sell_rsi=75.0, reset_rsi=68.0
```

- [ ] **Step 5: Commit**

```powershell
git add huntbot/state.py huntbot/__main__.py
git commit -m "feat: add backtest and strategy selection CLI"
```

## Task 7: Trader Dry-Run And Live Confirmation

**Files:**
- Create: `huntbot/trader.py`
- Create: `tests/test_trader.py`
- Modify: `huntbot/__main__.py`

- [ ] **Step 1: Write trader safety tests**

Create `tests/test_trader.py`:

```python
from decimal import Decimal

from huntbot.models import StrategyConfig
from huntbot.trader import WatchResult, run_watch_once


class FakeClient:
    def get_accounts(self):
        return [{"currency": "HUNT", "balance": "1000"}]

    def get_order_chance(self, market):
        return {"market": {"ask_types": ["market"], "bid": {"min_total": "5000"}}}

    def market_sell(self, market, volume):
        return {"uuid": "order-1", "market": market, "volume": volume}


def test_dry_run_never_places_order():
    result = run_watch_once(
        client=FakeClient(),
        strategy=StrategyConfig("KRW-HUNT", 60, 14, 70.0, 60.0),
        rsi_value=75.0,
        current_price=Decimal("3000"),
        live=False,
        confirm_phrase=None,
    )
    assert isinstance(result, WatchResult)
    assert result.order_uuid is None
    assert result.action == "dry_run_sell_signal"


def test_live_requires_confirmation_phrase():
    result = run_watch_once(
        client=FakeClient(),
        strategy=StrategyConfig("KRW-HUNT", 60, 14, 70.0, 60.0),
        rsi_value=75.0,
        current_price=Decimal("3000"),
        live=True,
        confirm_phrase="WRONG",
    )
    assert result.action == "confirmation_required"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_trader.py -v
```

Expected: FAIL because `huntbot.trader` does not exist.

- [ ] **Step 3: Implement trader orchestration**

Create `huntbot/trader.py`:

```python
from dataclasses import dataclass
from decimal import Decimal

from huntbot.models import StrategyConfig
from huntbot.state import load_cycle, save_cycle
from huntbot.strategy import evaluate_sell_signal


LIVE_CONFIRMATION = "SELL KRW-HUNT"


@dataclass(frozen=True)
class WatchResult:
    action: str
    rsi_value: float | None
    holding_value: Decimal
    available_quantity: Decimal
    sell_quantity: Decimal
    order_uuid: str | None = None


def run_watch_once(
    *,
    client,
    strategy: StrategyConfig,
    rsi_value: float | None,
    current_price: Decimal,
    live: bool,
    confirm_phrase: str | None,
) -> WatchResult:
    accounts = client.get_accounts()
    hunt_balance = _find_balance(accounts, "HUNT")
    holding_value = hunt_balance * current_price
    cycle = load_cycle()
    decision = evaluate_sell_signal(
        rsi_value=rsi_value,
        sell_rsi=strategy.sell_rsi,
        reset_rsi=strategy.reset_rsi,
        holding_value=holding_value,
        available_quantity=hunt_balance,
        cycle=cycle,
    )
    save_cycle(decision.next_cycle)

    if not decision.should_sell:
        return WatchResult(decision.reason, rsi_value, holding_value, hunt_balance, Decimal("0"))

    if not live:
        return WatchResult("dry_run_sell_signal", rsi_value, holding_value, hunt_balance, decision.sell_quantity)

    if confirm_phrase != LIVE_CONFIRMATION:
        return WatchResult("confirmation_required", rsi_value, holding_value, hunt_balance, decision.sell_quantity)

    chance = client.get_order_chance(strategy.market)
    ask_types = chance.get("market", {}).get("ask_types", [])
    if "market" not in ask_types:
        return WatchResult("market_sell_unsupported", rsi_value, holding_value, hunt_balance, decision.sell_quantity)

    order = client.market_sell(strategy.market, _format_decimal(decision.sell_quantity))
    return WatchResult("live_order_sent", rsi_value, holding_value, hunt_balance, decision.sell_quantity, order_uuid=order.get("uuid"))


def _find_balance(accounts: list[dict], currency: str) -> Decimal:
    for account in accounts:
        if account.get("currency") == currency:
            return Decimal(str(account.get("balance", "0")))
    return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
```

- [ ] **Step 4: Wire watch command**

Replace `huntbot/__main__.py` with:

```python
import argparse
import time
from decimal import Decimal

from huntbot.backtest import run_candidate_search
from huntbot.config import MARKET, RSI_PERIOD, load_environment
from huntbot.indicators import rsi
from huntbot.market_data import fetch_recent_candles
from huntbot.models import StrategyConfig
from huntbot.state import load_strategy, save_strategy
from huntbot.trader import LIVE_CONFIRMATION, run_watch_once
from huntbot.upbit_client import UpbitClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huntbot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backtest")

    select = subparsers.add_parser("select")
    select.add_argument("--unit", type=int, choices=[5, 15, 60], required=True)
    select.add_argument("--sell-rsi", type=float, required=True)
    select.add_argument("--reset-rsi", type=float, required=True)

    watch = subparsers.add_parser("watch")
    mode = watch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    watch.add_argument("--loop", action="store_true")
    return parser


def main() -> int:
    load_environment()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "backtest":
        return run_backtest_command()
    if args.command == "select":
        strategy = StrategyConfig(
            market=MARKET,
            unit=args.unit,
            rsi_period=RSI_PERIOD,
            sell_rsi=args.sell_rsi,
            reset_rsi=args.reset_rsi,
        )
        save_strategy(strategy)
        print(f"Saved strategy: unit={args.unit}, sell_rsi={args.sell_rsi}, reset_rsi={args.reset_rsi}")
        return 0
    if args.command == "watch":
        return run_watch_command(live=args.live, loop=args.loop)
    raise RuntimeError(f"unsupported command: {args.command}")


def run_backtest_command() -> int:
    client = UpbitClient()
    pages_by_unit = {60: 22, 15: 88, 5: 264}
    candles_by_unit = {
        unit: fetch_recent_candles(client, MARKET, unit=unit, pages=pages)
        for unit, pages in pages_by_unit.items()
    }
    results = run_candidate_search(candles_by_unit)
    print("unit sell_rsi reset_rsi return_pct final_value sells cash remaining_hunt max_dd")
    for result in results[:20]:
        print(
            f"{result.unit} {result.sell_rsi:.1f} {result.reset_rsi:.1f} "
            f"{result.final_return_pct:.2f} {result.final_total_value.quantize(Decimal('1'))} "
            f"{result.sell_count} {result.cash.quantize(Decimal('1'))} "
            f"{result.remaining_quantity:.8f} {result.max_drawdown_pct:.2f}"
        )
    return 0


def run_watch_command(*, live: bool, loop: bool) -> int:
    client = UpbitClient()
    while True:
        strategy = load_strategy()
        candles = fetch_recent_candles(client, strategy.market, unit=strategy.unit, pages=1)
        current_rsi = rsi([float(candle.close) for candle in candles], period=strategy.rsi_period)[-1]
        current_price = candles[-1].close
        confirm_phrase = None
        if live:
            print(f"Live order confirmation required. Type exactly: {LIVE_CONFIRMATION}")
            confirm_phrase = input("> ").strip()
        result = run_watch_once(
            client=client,
            strategy=strategy,
            rsi_value=current_rsi,
            current_price=current_price,
            live=live,
            confirm_phrase=confirm_phrase,
        )
        print(
            f"action={result.action} rsi={result.rsi_value} "
            f"holding_value={result.holding_value.quantize(Decimal('1'))} "
            f"available_hunt={result.available_quantity} sell_quantity={result.sell_quantity} "
            f"order_uuid={result.order_uuid}"
        )
        if not loop:
            return 0
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run trader tests**

Run:

```powershell
pytest tests/test_trader.py -v
```

Expected: PASS.

- [ ] **Step 6: Run all tests**

Run:

```powershell
pytest -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add huntbot/trader.py tests/test_trader.py huntbot/__main__.py
git commit -m "feat: add dry-run and live sell flow"
```

## Task 8: Final Verification With Real Dry-Run

**Files:**
- Modify: `README.md` if commands or setup changed during implementation.

- [ ] **Step 1: Install dependencies**

Run:

```powershell
python -m pip install -e ".[test]"
```

Expected: dependencies install successfully.

- [ ] **Step 2: Verify no secrets are tracked**

Run:

```powershell
git status --short
git ls-files .env
```

Expected: `.env` is not listed by `git ls-files`.

- [ ] **Step 3: Run all tests**

Run:

```powershell
pytest -v
```

Expected: PASS.

- [ ] **Step 4: Run backtest**

Run:

```powershell
python -m huntbot backtest
```

Expected: top 20 RSI candidate table for `KRW-HUNT`.

- [ ] **Step 5: Select one strategy from the table**

Run with the user's chosen row:

```powershell
python -m huntbot select --unit 60 --sell-rsi 75 --reset-rsi 68
```

Expected: selected strategy saved to `data/state/strategy.json`.

- [ ] **Step 6: Run dry-run**

Run:

```powershell
python -m huntbot watch --dry-run
```

Expected: no order is placed. Output shows RSI, valuation, available HUNT, and whether a sell would occur.

- [ ] **Step 7: Only after user approval, run live once**

Run:

```powershell
python -m huntbot watch --live
```

Expected: the CLI prints order details and asks for `SELL KRW-HUNT`. If the user enters any other text, no order is sent.

## Plan Self-Review

- Spec coverage: market, RSI period, candle units, 6-month backtest, 3,000,000 KRW assumption, 50% sells, reset threshold search, 500,000 KRW stop-sell, final-return ranking, dry-run default, live confirmation, and sell-only scope are covered.
- Placeholder scan: no task uses unfinished placeholder markers; the watch CLI replacement is fully specified.
- Type consistency: `StrategyConfig`, `BacktestResult`, `CycleState`, and `WatchResult` names match across tasks.
