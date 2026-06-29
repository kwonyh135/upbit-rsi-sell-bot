# Live Completed-Candle Crash Protection Design

## Goal

Replace the live bot's two ten-second crash observations with two consecutive
completed five-minute candle observations. Use a 6% same-candle high-to-close
drop or a 5% average-buy-price-to-close loss, then liquidate all available HUNT
and enter the existing manual emergency halt.

There is no six-hour unlock restriction. The existing local
`unlock-emergency` command may clear the halt immediately after the emergency
order has completed and no pending order remains.

## Risk Observation

Fetch recent five-minute candles before normal RSI action selection and retain
only candles completed at `now`. For each completed candle calculate:

- `high_drop_pct = (high - close) / high * 100`, when `close < high`.
- `average_loss_pct = (average_buy_price - close) / average_buy_price * 100`,
  when the account has a positive average buy price and `close` is lower.

A candle is risky when `high_drop_pct >= 6` or `average_loss_pct >= 5`.

The two newest risky candles confirm an emergency only when their timestamps
are exactly five minutes apart. A missing no-trade candle breaks the sequence.
The latest risky candle alone produces `emergency_pending`, records one
confirmation, and blocks every normal RSI order until another completed candle
is available. A healthy latest candle resets confirmations to zero.

The live orderbook remains the source of displayed current price and market
order minimum-value checks. It does not decide the completed-candle risk.

## Emergency Workflow

Confirmed risk has priority over all RSI phases and creates one market sell for
the entire available HUNT balance through the existing pending-order workflow.
The phase changes to `emergency_halt` only after Upbit reports completion or a
cancelled market order with fills.

If confirmed risk is present without a HUNT position, live mode enters
`emergency_halt` without submitting an order. Once the persisted phase is
`emergency_halt`, later cycles return halted immediately and do not send repeat
emergency notifications or attempt another liquidation.

Order submission identifiers, reconciliation, minimum-order protection,
Telegram best-effort delivery, and atomic state writes remain unchanged.

## Recovery

Keep the existing `unlock-emergency` command and confirmation phrase
`UNLOCK KRW-HUNT`. It must continue to require:

- Current phase is `emergency_halt`.
- `pending_order` is null.
- Exact local confirmation phrase.

Unlock resets the phase to `sell_1` and clears emergency counters immediately.
No timer, automatic restart, or Telegram unlock command is added.

## Backtest and Validation

Update the research simulator so fixed/adaptive confirmation streaks also reset
when candle timestamps are not exactly one candle unit apart. Run the exact
live candidate `high drop 6% / average loss 5% / two completed candles` on the
latest saved six-month snapshot.

Report the no-protection baseline and exact candidate under:

- Immediate manual-unlock proxy, representing the most aggressive possible
  operator restart.
- Permanent halt reference, representing no operator restart during the test.
- 0.05%, 0.30%, and 1.00% crash-exit slippage.

The 5% average-loss value was selected by the user after the broader parameter
study and was not the earlier balanced winner. Its focused result must be
reported without relabeling it as historically optimal.

## Tests

Add deterministic tests for:

- 6% high-to-close and 5% average-loss boundaries.
- One risky completed candle blocking normal RSI orders.
- Two adjacent risky completed candles confirming one full liquidation.
- A timestamp gap resetting the sequence.
- Repeated service cycles on the same candles not increasing confirmation.
- `emergency_halt` suppressing repeat notification and order behavior.
- Immediate manual unlock with no cooldown.
- Existing RSI phase and pending-order behavior remaining unchanged.
