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
