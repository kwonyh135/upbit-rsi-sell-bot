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
python -m huntbot backtest-buyback
python -m huntbot select --unit 60 --sell-rsi 75 --reset-rsi 68
python -m huntbot watch --dry-run
python -m huntbot watch --live
python -m huntbot watch-buyback-5m --dry-run
python -m huntbot watch-buyback-5m --live
```

## 5m Buyback Mode

The 5-minute buyback mode uses the best simulated 5-minute thresholds:

- Sell signal: RSI 14 is `65` or higher.
- Buyback signal: RSI 14 is `49` or lower.
- Sell amount: 50% of current HUNT balance.
- Buyback amount: limited to the estimated KRW cash recorded after the last bot sell.

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

## Event Visualization

Generate the 5-minute split buyback event report:

```powershell
python -m huntbot report-split-5m
```

Open `docs/split-buyback-events-5m.html` to see the full backtest summary and recent 90-day buy/sell event table.
