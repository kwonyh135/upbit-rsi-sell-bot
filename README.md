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
