# KRW-HUNT Unattended Auto-Trading Design

## Goal

Run the existing Upbit KRW-HUNT 5-minute split RSI strategy unattended on a Windows laptop, automatically place eligible orders, and notify the owner through Telegram.

The bot must continue from the current persisted phase. At the time this design was approved, the expected phase was `buy_2`.

## Trading Strategy

- Market: `KRW-HUNT`
- Candle unit: 5 minutes
- RSI period: 14
- Evaluate signals only from completed 5-minute candles.
- First sell: RSI 60 or higher, sell 50% of the current available HUNT balance.
- Second sell: RSI 65 or higher, sell the remaining available HUNT balance.
- First buy: RSI 45 or lower, spend 50% of the current available KRW balance.
- Second buy: RSI 40 or lower, spend the current remaining available KRW balance.
- KRW deposited after the bot starts is included in the available balance and may be used by the next buy step.
- The live strategy does not require interactive `BUY KRW-HUNT` or `SELL KRW-HUNT` confirmation.

## Runtime Model

Add an explicit unattended live command rather than changing the existing interactive live command. The unattended command runs continuously, polls frequently enough to detect a newly completed 5-minute candle, and evaluates each completed candle at most once.

The runtime stores:

- Current strategy phase.
- Last completed candle timestamp evaluated.
- Pending order UUID and intended phase transition, when applicable.
- Last successful trade information needed for recovery and notifications.

State writes use an atomic temporary-file replacement so an interrupted write cannot leave partial JSON.

## Order Safety

Before sending an order, the bot verifies:

- The signal belongs to a newly completed candle.
- The current phase matches the intended action.
- The calculated quantity or KRW amount is positive.
- The order satisfies Upbit's current minimum order and supported order type.
- There is no unresolved pending order.

After sending an order:

1. Save the order UUID as pending.
2. Query Upbit for the final order state and executed amounts.
3. Advance the strategy phase only after confirmed completion.
4. Retain the pending order and stop new trading if completion cannot be determined.

The bot must never blindly resend an order after a timeout or ambiguous API response. On restart, it resolves the stored pending order through Upbit before evaluating another signal.

## Telegram Notifications

Configuration is stored only in `.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Send notifications for:

- Bot startup, including current phase and balances.
- Clean shutdown.
- Order submission.
- Confirmed order completion, including action, RSI, candle time, price, executed quantity, executed KRW amount, order UUID, and next phase.
- API, network, state, or order-reconciliation errors.
- Recovery after an error condition.

Repeated identical errors are rate-limited to avoid notification flooding. Secrets are never included in messages or logs.

Telegram delivery failure must not cause a duplicate trade or roll back a completed phase transition. Notification retries are independent from trading state.

## Error Handling

- Transient market-data and account API errors use bounded exponential backoff.
- Repeated failures pause signal processing while the process remains alive.
- Ambiguous order results enter reconciliation mode and block further orders.
- Invalid or missing state stops trading and sends an error notification.
- An unavailable Telegram API is logged and retried without disabling trading.
- Unexpected exceptions are logged with timestamps and trigger a Telegram error notification when possible.

## Windows Operation

Use Windows Task Scheduler:

- Start the unattended bot at user logon.
- Start in the repository worktree directory.
- Use the known bundled Python executable unless a project virtual environment is created.
- Restart the task after failure with a bounded delay.
- Prevent multiple simultaneous bot processes.
- Write stdout and errors to rotating log files.

Configure Windows power settings so the laptop does not sleep while connected to AC power. The bot cannot operate while Windows is sleeping, powered off, or disconnected from the network.

## Commands

Keep the existing commands:

- `watch-buyback-5m --dry-run`
- `watch-buyback-5m --live`
- `sync-buyback-state`

Add the following separate unattended command:

```powershell
python -m huntbot run-auto-5m
```

This separation prevents accidental conversion of the interactive command into unattended live trading.

## Testing

Automated tests cover:

- Completed-candle selection and one-time processing.
- RSI threshold boundaries for all four phases.
- Full KRW balance behavior for both buy phases.
- HUNT balance behavior for both sell phases.
- Pending-order persistence and restart reconciliation.
- No duplicate order after timeout or restart.
- Phase changes only after confirmed order completion.
- Telegram payloads for startup, shutdown, trade, error, and recovery.
- Telegram failure isolation from trading state.
- Atomic state persistence.
- Task Scheduler command generation or installation script behavior without creating a real task during unit tests.

Before unattended live activation:

1. Run the full automated test suite.
2. Run the unattended loop in a no-order simulation mode.
3. Verify Telegram startup, trade-simulation, error, and recovery messages.
4. Confirm the current Upbit balances and persisted phase.
5. Enable the scheduled unattended live task only after those checks pass.

## Out of Scope

- Cloud hosting.
- Multiple markets.
- Dynamic RSI optimization.
- A web dashboard.
- Remote Telegram commands that can place or cancel orders.
