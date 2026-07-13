# Bitget BTC Paper Trading

This is a research-only virtual trading mode for the Bitget BTCUSDT Donchian trend strategy.

It does not use Bitget API keys and does not submit real orders.

## Strategy

- Market: `BTCUSDT`
- Exchange data: Bitget public futures candles
- Candle unit: completed 5-minute candles
- Signal unit: completed 4-hour Donchian breakout
- Default lookback: `40`
- Exposure: `1x`
- Initial virtual equity: `3000 USDT`

Long and short positions are simulated in a local state file. Fees and slippage are included in the virtual fills.

## Local One-Shot Check

Use cached candles when you want to verify the paper engine without calling the network:

```powershell
.\.venv\Scripts\python.exe -m huntbot run-bitget-btc-paper `
  --once `
  --candles data\backtests\bitget-btcusdt-5m-2y-plus-warmup.csv `
  --lookback 40 `
  --initial-equity 3000
```

Use live public Bitget candles:

```powershell
.\.venv\Scripts\python.exe -m huntbot run-bitget-btc-paper `
  --once `
  --lookback 40 `
  --initial-equity 3000
```

## Local Loop

```powershell
.\.venv\Scripts\python.exe -m huntbot run-bitget-btc-paper `
  --loop `
  --lookback 40 `
  --initial-equity 3000 `
  --poll-seconds 300
```

## Runtime Files

- State: `data/state/bitget-btc-paper.json`
- Log: `logs/bitget-btc-paper.log`

Both paths are ignored by git.

## Reading Output

Each run prints a compact line:

```text
mode=paper market=BTCUSDT position=long action=open_long price=... equity=... return_pct=... mdd=... signal=...
```

- `position`: current virtual position, one of `flat`, `long`, or `short`
- `action`: new virtual fill, or `None` when no new signal fired
- `equity`: current virtual account value
- `return_pct`: virtual return versus initial equity
- `mdd`: current drawdown from the virtual account peak
- `signal`: latest Donchian signal timestamp

## AWS Later

After local paper mode behaves correctly, it can be deployed to AWS as a separate `systemd` timer from the Upbit HUNT live bot. Keep it separate so the BTC research service cannot affect the HUNT real-money service.

The installer copies these units:

- `huntbot-btc-paper.service`: runs one virtual trading cycle
- `huntbot-btc-paper.timer`: runs the service hourly

Install or refresh the code on EC2:

```bash
cd ~/huntbot-upload
git fetch origin
git checkout codex/upbit-rsi-sell-bot
git pull --ff-only origin codex/upbit-rsi-sell-bot
sudo bash deploy/install-ubuntu.sh ~/huntbot-upload
```

Run one AWS paper cycle manually first:

```bash
sudo -u huntbot bash -lc 'cd /opt/huntbot/app && /opt/huntbot/venv/bin/python -m huntbot run-bitget-btc-paper --once --lookback 40 --initial-equity 3000'
```

Start hourly paper trading:

```bash
sudo systemctl enable --now huntbot-btc-paper.timer
```

Check the timer:

```bash
sudo systemctl status huntbot-btc-paper.timer
sudo systemctl list-timers huntbot-btc-paper.timer
```

Check the most recent paper run:

```bash
sudo systemctl status huntbot-btc-paper.service --no-pager -l
sudo journalctl -u huntbot-btc-paper.service -n 50 --no-pager
```

Check the virtual ledger files:

```bash
sudo cat /opt/huntbot/shared/data/state/bitget-btc-paper.json
sudo tail -n 50 /opt/huntbot/shared/logs/bitget-btc-paper.log
```

Stop hourly paper trading:

```bash
sudo systemctl disable --now huntbot-btc-paper.timer
```

These AWS runtime paths are the authoritative paper trading records:

- `/opt/huntbot/shared/data/state/bitget-btc-paper.json`
- `/opt/huntbot/shared/logs/bitget-btc-paper.log`
