# HUNT 114 KRW Fixed-Floor Exit Design

## Goal

Update the live KRW-HUNT strategy to use earlier RSI sells and replace the
percentage-based crash protection with a fixed 114 KRW floor exit.

## Live Rules

- Keep the 30-second continuous provisional-RSI confirmation.
- Change `sell_1` from RSI 60 to RSI 56 and sell half of the HUNT balance.
- Change `sell_2` from RSI 65 to RSI 61 and sell the remaining HUNT balance.
- Keep `buy_1` at RSI 45 and `buy_2` at RSI 40.
- When the current order-book best bid is 114 KRW or lower and HUNT is held,
  immediately submit an `emergency_sell` for the full balance.
- After the floor exit, retain `emergency_halt`; no automatic re-entry occurs.

## Replaced Protection

The fixed floor exit replaces the current percentage-based completed-candle
protection. The old high-drop, average-loss, and two-candle confirmation logic
must not independently trigger a live emergency order after this change.

## Ordering And Failure Handling

The floor check runs after a valid, fresh order-book best bid is available and
before fetching candles or evaluating normal RSI signals. It uses the existing
pending-order persistence and reconciliation workflow. A pending order or an
existing `emergency_halt` continues to block any new order.

If there is no HUNT balance at or below 114 KRW, the bot enters
`emergency_halt` without submitting an order, matching the existing confirmed
emergency behavior.

## Verification

Add focused tests for:

- Updated sell thresholds and unchanged buy thresholds.
- A best bid of 114 KRW triggering a full emergency sell before RSI logic.
- A best bid above 114 KRW not triggering the floor exit.
- No-HUNT floor trigger entering `emergency_halt` without an order.
- Existing pending-order and halt protections remaining intact.

Run focused tests, the full suite, an AWS dry-run one-shot check, then restart
the live systemd service only after the state has no pending order.
