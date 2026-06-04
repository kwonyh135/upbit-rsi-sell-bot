# Upbit RSI HUNT Sell Bot Design

## Goal

Build a Python CLI bot for `KRW-HUNT` that finds RSI overheat sell conditions through backtesting, then uses the selected condition to sell half of the user's actual Upbit HUNT balance when the live RSI reaches that condition.

This first version is sell-only. It does not buy coins, rebalance assets, withdraw funds, or automatically change strategy after deployment.

## User Requirements

- Market: `KRW-HUNT`
- Strategy type: RSI overheat sell
- RSI period: `14`
- Candle units to test: `60`, `15`, and `5` minutes
- Backtest period: recent 6 months
- Backtest starting assumption: the user bought `3,000,000 KRW` worth of HUNT at the first backtest candle close
- Sell action: sell `50%` of remaining HUNT quantity
- Re-entry rule: after a sell, the bot may sell again only after RSI falls below a reset threshold and later reaches the sell threshold again
- Stop-sell rule: do not sell if remaining HUNT valuation is below `500,000 KRW`
- Selection objective: rank backtest results by final return
- Live order type: Upbit market sell
- Interface: CLI

## External API Facts

The implementation will use Upbit Open API.

- Minute candles: `GET /v1/candles/minutes/{unit}`
  - Units include `5`, `15`, and `60`.
  - Each request can return up to `200` candles.
  - Candles may be absent for intervals without trades.
- Account balances: `GET /v1/accounts`
  - Requires an API key with asset-read permission.
- Order chance: `GET /v1/orders/chance`
  - Used to confirm market support, ask order support, and minimum order values.
- Market sell: `POST /v1/orders`
  - `market=KRW-HUNT`
  - `side=ask`
  - `ord_type=market`
  - `volume=<HUNT quantity>`
  - Requires order permission.

## Architecture

The project will be a small Python package with CLI commands.

- `upbit_client`
  - Public candle requests
  - Authenticated balance, order chance, and order requests
  - JWT signing
  - Rate-limit friendly retries
- `market_data`
  - Fetches 6 months of candles for each configured unit
  - Stores raw candle cache locally to reduce repeated API calls
  - Normalizes candle order from oldest to newest
- `indicators`
  - Computes RSI 14 using close prices
- `backtest`
  - Simulates the 3,000,000 KRW initial HUNT holding
  - Tests candidate sell thresholds and reset thresholds
  - Applies 50% sell and 500,000 KRW stop-sell rules
  - Produces ranked results by final return
- `strategy`
  - Holds the selected candle unit, sell threshold, and reset threshold
  - Decides whether current RSI permits a sell
- `state`
  - Persists whether the current RSI overheat cycle already sold
  - Stores last sell timestamp and order UUID for audit
- `trader`
  - Loads Upbit credentials from `.env`
  - Reads actual HUNT balance
  - Checks current price and valuation
  - Executes dry-run or live market sell

## CLI Commands

Planned commands:

```powershell
python -m huntbot backtest
python -m huntbot select --unit 60 --sell-rsi 75 --reset-rsi 68
python -m huntbot watch --dry-run
python -m huntbot watch --live
```

`backtest` fetches candles and prints a ranked table.

`select` writes the chosen strategy into a local config file.

`watch --dry-run` checks live conditions and prints what would happen without placing an order.

`watch --live` can place a market sell order. Before sending a live order, it must print the market, RSI, current valuation, available HUNT quantity, and sell quantity, then require the exact confirmation phrase `SELL KRW-HUNT`.

By default, `watch` runs once and exits. Continuous monitoring is enabled only when the user passes a loop flag.

## Backtest Candidate Search

RSI period is fixed at `14`.

Candidate ranges:

- Sell RSI threshold: `65` through `90`
- Reset RSI threshold: values below the sell threshold, such as sell threshold minus `3`, `5`, `7`, `10`, and `15`

Invalid combinations are skipped when the reset threshold is not below the sell threshold.

Each candle unit is tested independently. Results must show at least:

- Candle unit
- Sell RSI threshold
- Reset RSI threshold
- Final return
- Final total value
- Number of sells
- Remaining HUNT quantity
- Cash after simulated sells
- Maximum drawdown

The main ranking is final return descending. Supporting metrics are shown to help the user avoid conditions that only win by overfitting.

## Live Trading Rules

The live bot uses actual Upbit account data, not the 3,000,000 KRW backtest assumption.

On each watch cycle:

1. Load selected strategy.
2. Fetch latest candles for the selected unit.
3. Compute RSI 14.
4. Fetch HUNT balance and current price.
5. Compute current HUNT valuation.
6. If valuation is below `500,000 KRW`, do not sell.
7. If RSI is below reset threshold, mark the strategy as ready for the next overheat sell.
8. If RSI is at or above sell threshold and the strategy is ready, prepare to sell `50%` of available HUNT.
9. In dry-run mode, log the planned sell only.
10. In live mode, require explicit confirmation, then submit a market sell order.
11. Record the order result and mark the current overheat cycle as already sold.

When continuous monitoring is enabled, the polling interval is `60` seconds. The implementation may later make this configurable, but the first version uses the fixed interval to keep behavior predictable.

## Safety Controls

- `.env` is git-ignored.
- API keys are never printed.
- API keys are never written into config, logs, or docs.
- Withdrawal permission is not required and should not be enabled.
- Live orders require `--live` plus an explicit confirmation phrase.
- Default command mode is dry-run.
- The bot only sells `KRW-HUNT`; it cannot buy.
- The bot refuses to trade if selected strategy config is missing.
- The bot refuses to trade if Upbit says market sell is unsupported for the market.
- The bot refuses to trade if calculated sell value is below Upbit's minimum order value.
- Logs include timestamps, RSI, threshold, valuation, sell quantity, and order UUID where available.

## User Setup Tasks

The user must do the following before live trading:

1. Create an Upbit Open API key.
2. Enable only these permissions:
   - Asset read
   - Order read
   - Order write
3. Do not enable withdrawal permission.
4. Register the public outbound IPv4 address used by the machine running the bot.
5. Put the key values into `.env` locally.
6. Run backtest and select one strategy.
7. Run dry-run mode and compare the output with the Upbit app or website.
8. Run live mode only after confirming balance, RSI, and sell quantity.

## Upbit IP Registration Guidance

Register the public IPv4 address that Upbit sees when this computer sends API requests.

Do not register:

- `192.168.x.x`
- `10.x.x.x`
- `172.16.x.x` through `172.31.x.x`
- `127.0.0.1`

Those are private or local addresses and are not valid for Upbit API access from the internet.

If the bot runs on the user's home PC, the user should check the public IP from that same PC immediately before creating the API key. If the internet provider changes the public IP later, Upbit API calls may fail until the key's allowed IP is updated.

If the bot runs on a VPS or cloud server, register the server's static public IPv4 address instead. This is more stable than a home internet address.

## Non-Goals

- No automatic buying
- No futures or margin trading
- No multi-coin portfolio logic
- No Telegram, Discord, or mobile notifications in the first version
- No web dashboard in the first version
- No automatic daily strategy replacement

## Testing Plan

- Unit tests for RSI calculation.
- Unit tests for strategy state transitions:
  - first overheat sells
  - repeated overheat without reset does not sell again
  - reset below threshold allows another later sell
  - valuation below 500,000 KRW blocks selling
- Backtest tests with fixed sample candles.
- Upbit client tests using mocked HTTP responses.
- Dry-run integration test using mocked balances and candles.

## Implementation Defaults

- Live confirmation phrase: `SELL KRW-HUNT`
- Default `watch` behavior: run once and exit
- Continuous watch interval: `60` seconds
