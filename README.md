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

## 5m Split Buyback Mode

The 5-minute buyback mode uses the best simulated 5-minute split thresholds:

- First sell signal: RSI 14 is `60` or higher, selling 50% of current HUNT balance.
- Second sell signal: RSI 14 is `65` or higher, selling the remaining HUNT balance.
- First buyback signal: RSI 14 is `45` or lower, buying with 50% of the current Upbit KRW balance.
- Second buyback signal: RSI 14 is `40` or lower, buying with the remaining fee-safe Upbit KRW balance.
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

The unattended mode checks prices every 10 seconds. Normal RSI signals use only completed 5-minute candles and each candle is processed once.

Start with one read-only cycle:

```powershell
& "C:\Users\김혜령\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m huntbot run-auto-5m --dry-run --once
```

Then run continuous dry-run for several days:

```powershell
& "C:\Users\김혜령\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m huntbot run-auto-5m --dry-run
```

Live auto mode:

```powershell
& "C:\Users\김혜령\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m huntbot run-auto-5m --live
```

Logs are written to `logs/huntbot-auto.log`.

## Emergency Crash Protection

Emergency protection has priority over RSI trading:

- Current price is at least `7%` below the highest price in the latest five 1-minute candles, or
- Current price is at least `10%` below the Upbit HUNT average buy price.
- The risk must be observed twice consecutively, 10 seconds apart.
- The first risky observation already blocks normal RSI orders.
- A confirmed risk sells all available HUNT at market.
- After confirmed liquidation, the bot enters `emergency_halt` and cannot buy again automatically.

Local unlock requires:

```text
UNLOCK KRW-HUNT
```

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
