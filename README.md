# HUNT RSI Sell Bot

This bot backtests and runs a 5-minute RSI split strategy for `KRW-HUNT`. It supports interactive trading and a separate unattended mode with Telegram notifications and emergency crash liquidation.

## Safety

- Do not enable withdrawal permission on the Upbit API key.
- Live auto trading needs Upbit order placement, account view, and order view permissions.
- Do not commit `.env`.
- Default trading mode is dry-run.
- `run-auto-5m --live` can place real market orders without interactive confirmation.
- Do not install the Windows scheduled task until dry-run and Telegram checks pass.

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
python -m huntbot backtest-buyback
python -m huntbot select --unit 60 --sell-rsi 75 --reset-rsi 68
python -m huntbot watch --dry-run
python -m huntbot watch --live
python -m huntbot watch-buyback-5m --dry-run
python -m huntbot watch-buyback-5m --live
python -m huntbot run-auto-5m --dry-run --once
python -m huntbot run-auto-5m --dry-run
python -m huntbot run-auto-5m --live
python -m huntbot unlock-emergency
```

## Read-only Local Dashboard

The dashboard runs as a process separate from the live trader. It reads Upbit
account, closed-order, order-detail, orderbook, and candle endpoints, plus the
local auto state and log. It never calls an order endpoint and never changes
the auto-trading state.

Install the dashboard dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Start the localhost-only dashboard:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dashboard.ps1
```

Open:

```text
http://127.0.0.1:8501
```

The page reads fresh data when it is first opened and when the `새로고침`
button is pressed. Other UI interactions do not call Upbit again. Dashboard
history is stored separately in `data/dashboard/huntbot-dashboard.sqlite3`.
Order UUID is the primary key, so restarting or resynchronizing does not
duplicate trades. Upbit read failures leave the last successful snapshot
visible with a stale warning.

The initial order sync scans the configured history in seven-day windows and
stores only orders whose identifier starts with `huntbot-`. A market order
with `state=cancel` is still counted when it has a positive executed volume or
trade details.

Performance calculation rules:

- Buy cost includes paid fees.
- Sell proceeds exclude paid fees.
- Realized P&L uses moving-average cost from synchronized fills.
- Current unrealized P&L uses the Upbit HUNT average buy price and current best
  bid.
- Results are marked partial if synchronized sells exceed known synchronized
  inventory.
- Deposits, withdrawals, manual orders, and holdings from before the sync
  range can prevent complete historical cost reconstruction.
- Maximum drawdown appears only after account-value snapshots span at least
  one hour.

Do not expose the dashboard outside localhost. `.env` is loaded only for API
authentication; keys and Telegram values are not rendered or logged by the
dashboard.

## 5m Split Buyback Mode

The 5-minute buyback mode uses the best simulated 5-minute split thresholds:

- First sell signal: RSI 14 is `60` or higher, selling 50% of current HUNT balance.
- Second sell signal: RSI 14 is `65` or higher, selling the remaining HUNT balance.
- First buyback signal: RSI 14 is `45` or lower, buying with 50% of the current Upbit KRW balance.
- Second buyback signal: RSI 14 is `40` or lower, buying with the remaining fee-safe Upbit KRW balance.
- If RSI recovers to `60` before the second buy, the bot starts the sell cycle with the HUNT already acquired.
- If RSI falls back to `45` after the first sell but before the second sell, the bot spends 50% of available KRW on a new first buy.
- New KRW deposits are included in the next buy step.

Open `docs/trading-flow-5m.html` in a browser to view the trading flow diagram.

## Split Buyback Backtest

Run:

```powershell
python -m huntbot backtest-split-buyback
python -m huntbot report-split-5m
```

This command evaluates two-step sell and two-step buyback RSI combinations through `2026-06-07 23:59:59 KST`, applying:

- Upbit KRW market fee assumption: `0.05%`
- Market-order slippage assumption: `0.05%`
- Initial HUNT valuation: `3,000,000 KRW`

Best result by unit from the latest run:

| Unit | Sell 1 | Sell 2 | Buy 1 | Buy 2 | Return | Final Value |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m | 60 | 65 | 45 | 40 | 314.94% | 12,448,348 KRW |
| 15m | 60 | 65 | 47 | 42 | 120.08% | 6,602,295 KRW |
| 60m | 62 | 67 | 46 | 41 | 64.70% | 4,940,922 KRW |

## Dry-run First

Before live trading, run dry-run until the bot output matches the Upbit app balance and price view.

```powershell
Copy-Item .env.example .env
notepad .env
python -m huntbot watch-buyback-5m --dry-run
```

Dry-run still needs valid Upbit API keys because it reads real balances, but it does not send orders.

## Unattended Auto Mode

The unattended mode checks prices every 10 seconds. Normal orders use provisional
five-minute RSI: completed candle closes initialize RSI and the validated current
best bid acts as the active candle close. The same buy or sell condition must be
observed continuously for at least 30 seconds before an order is submitted. A
condition change, data error, emergency risk, or observation gap over 20 seconds
resets confirmation. Logs show `status=confirming` while the timer is active.

Only normal RSI timing changed. Split sizing and the `60`/`65`/`45`/`40`
thresholds are unchanged, and completed-candle emergency protection still runs
before every normal RSI decision.

Start with one read-only cycle:

```powershell
.\.venv\Scripts\python.exe -m huntbot run-auto-5m --dry-run --once
```

Then run continuous dry-run for several days:

```powershell
.\.venv\Scripts\python.exe -m huntbot run-auto-5m --dry-run
```

Live auto mode:

```powershell
.\.venv\Scripts\python.exe -m huntbot run-auto-5m --live
```

Logs are written to `logs/huntbot-auto.log`.

## Emergency Crash Protection

Emergency protection has priority over RSI trading:

- A completed five-minute candle closes at least `6%` below its own high, or
- A completed five-minute candle closes at least `12%` below the Upbit HUNT average buy price.
- The two newest risky completed candles must be exactly five minutes apart. A missing no-trade candle breaks confirmation.
- The first risky completed candle already blocks normal RSI orders without placing an emergency order.
- A confirmed risk sells all available HUNT at market.
- After confirmed liquidation, the bot enters `emergency_halt` and cannot buy again automatically.
- Repeated 10-second polling of the same completed candle does not increase confirmations.

Local unlock has no cooldown and requires:

```text
UNLOCK KRW-HUNT
```

Unlock is allowed only after the emergency order is reconciled and
`pending_order` is null. It resets the strategy to `sell_1`; no Telegram or
automatic unlock is available.

## Telegram

Create a Telegram bot and add these values to `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

The bot sends startup, shutdown, order, completion, emergency, error, and recovery messages. Telegram delivery failure does not change trading state or resend an order.

## Windows Auto Start

After continuous dry-run and Telegram verification:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-auto-task.ps1
```

Remove it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\remove-auto-task.ps1
```

The installer creates `HuntBot-Auto-5m` at user logon with restart-on-failure and one-instance settings. Keep the laptop connected to AC power and disable sleep while plugged in.

## Event Visualization

Generate the 5-minute split buyback event report:

```powershell
python -m huntbot report-split-5m
```

Open `docs/split-buyback-events-5m.html` to see the full backtest summary and recent 90-day buy/sell event table.

## Bitget BTC Futures Research

Run the research-only six-month BTCUSDT perpetual-futures comparison:

```powershell
.\.venv\Scripts\python.exe -m huntbot backtest-bitget-btc --months 6
```

This compares cash, BTC 1x buy-and-hold, long-only, short-only,
bidirectional, and regime-filtered bidirectional RSI strategies. It uses
public Bitget data, 1x exposure, taker fees, adverse slippage, and historical
funding. It does not load API secrets, place orders, modify the HUNT bot, or
deploy to AWS.

## AWS EC2 Ubuntu

AWS에서는 `systemd`가 봇을 한 개만 실행하고 장애 시 재시작합니다. API 키, 거래 상태, 로그는 코드 배포와 분리된 `/opt/huntbot/shared`에 유지됩니다.

```bash
sudo bash deploy/install-ubuntu.sh
```

설치 직후 라이브 거래는 자동 시작되지 않습니다. Elastic IP 설정, 기존 봇 정지, 상태파일 이전, dry-run, 서비스 시작 순서는 [AWS EC2 운영 런북](docs/aws-ec2-runbook.md)을 따르세요.
