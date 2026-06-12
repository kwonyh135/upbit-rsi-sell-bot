# Local Operations Dashboard Design

## Goal

Provide a Korean, read-only dashboard for the live `KRW-HUNT` bot without
sharing runtime state or failure modes with the trading process.

## Architecture

The dashboard runs as a separate Streamlit process bound to `127.0.0.1`.
It reads `data/state/auto-trading.json` and `logs/huntbot-auto.log`, calls
only Upbit account/order/orderbook/candle read endpoints, and writes only to
`data/dashboard/huntbot-dashboard.sqlite3`.

The dashboard never imports or calls order submission, state save, emergency
unlock, or service lifecycle functions.

## Components

- `huntbot/dashboard_store.py`: SQLite schema, UUID upserts, snapshots, and
  query helpers.
- `huntbot/dashboard_collector.py`: read-only Upbit synchronization, state and
  log inspection, action classification, and stale fallback.
- `huntbot/dashboard_metrics.py`: trade normalization, moving-average realized
  P&L, current unrealized P&L, returns, equity curve, and drawdown.
- `huntbot/dashboard_app.py`: Streamlit UI, Korean labels, filters, CSV export,
  charts, status colors, and 15-second refresh.
- `scripts/start-dashboard.ps1`: localhost-only launcher.

## Data Model

`orders` uses the Upbit order UUID as its primary key. Each row stores the
bot identifier, action, side, order state, timestamps, execution quantity,
execution funds, average execution price, fee, and next phase. Orders with
state `cancel` and positive executed volume or trades are treated as filled.

`account_snapshots` stores balances, average buy price, best bid, RSI, account
value, and collection status. `candles` stores completed five-minute OHLC and
RSI values keyed by candle timestamp. `sync_meta` stores successful sync and
error timestamps.

Initial order synchronization walks backward in seven-day windows. Only orders
whose identifier starts with `huntbot-` are stored. Each candidate is fetched
through the order-detail endpoint so trade funds and fees take precedence over
log-derived values. Repeated synchronization is idempotent.

## Status And Staleness

The dashboard considers the live service healthy only when a matching
`run-auto-5m --live` process is visible and the latest normal log heartbeat is
no older than 35 seconds. A recent error changes the status to warning or
danger until a later normal heartbeat appears. API failures retain the last
successful snapshot and display its age and the latest collection error.

## Performance Calculations

Buy cost is execution funds plus fees. Sell proceeds are execution funds minus
fees. Realized P&L uses moving-average cost for inventory established by the
collected order history. If a sell exceeds known inventory, that unmatched
quantity is excluded from realized P&L and the result is marked partial.

Current unrealized P&L uses the Upbit HUNT average buy price and current best
bid. Total P&L is known realized P&L plus current unrealized P&L. Return is
total P&L divided by cumulative collected buy cost. The UI states these rules
and warns that deposits, withdrawals, and orders outside the synchronized
history can make cumulative results incomplete.

Maximum drawdown is shown only when at least two account-value snapshots exist
and span at least one hour.

## UI

The top area shows freshness, live health, phase, pending order, emergency
state, balances, average buy price, best bid, completed-candle RSI, next action,
and last error. Tables and charts follow, with compact columns that stack on
mobile. Charts cover price with trade markers, RSI thresholds, cumulative
realized P&L, account value, and emergency events.

No controls can place orders, change phase, unlock emergency state, stop, or
restart the bot.

## Testing

Tests use fake clients and temporary files/databases. They cover UUID
idempotency, filled `cancel` orders, action parsing, historical window sync,
API failure fallback, empty data, moving-average P&L, partial inventory, fees,
drawdown gating, process/log health, and secret redaction. No test calls Upbit.
