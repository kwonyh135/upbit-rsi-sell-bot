# Live RSI Hold-30-Seconds Design

## Goal

Replace normal live RSI decisions based only on completed five-minute candles with the backtest winner: a provisional intrabar RSI condition that must remain continuously valid for 30 seconds. Preserve the current order-reconciliation workflow and completed-candle crash protection without weakening either one.

## Scope

This change affects the unattended `run-auto-5m` live and dry-run paths. It does not change the market (`KRW-HUNT`), RSI thresholds, split order sizes, fee-safe buy sizing, emergency thresholds, Telegram destination, AWS service command, or local dashboard.

## Signal Source

Each service cycle continues to fetch the current best bid and recent five-minute candles. Completed candles initialize Wilder RSI, and the current best bid acts as the provisional close for the active five-minute candle. The active signal candle is derived from the timestamp of the validated orderbook price rather than the local clock.

The existing action thresholds remain:

- `sell_1` at RSI 60 or higher when allowed by phase;
- `sell_2` at RSI 65 or higher;
- `buy_1` at RSI 45 or lower when allowed by phase;
- `buy_2` at RSI 40 or lower while phase is `buy_2`.

## Persistent Confirmation State

`AutoTradeState` gains four optional, backward-compatible fields:

- `rsi_signal_action`;
- `rsi_signal_started_at`;
- `rsi_signal_last_seen_at`;
- `rsi_signal_candle`.

Old AWS state files load these fields as `None`. The existing `last_completed_candle` JSON field remains for deployment compatibility, but for normal RSI orders it represents the candle in which the last action was consumed.

When a threshold first appears, the bot stores the action, start time, observation time, and signal candle. On later cycles, the same candidate action updates the last-observed time. It becomes executable only after at least 30 wall-clock seconds have elapsed from the start.

The timer resets when:

- the threshold is no longer satisfied;
- the candidate action changes;
- the gap since the previous successful observation exceeds 20 seconds;
- market data is missing or stale;
- completed-candle risk is pending, confirmed, or invalid;
- the signal candle was already consumed by an order decision.

The same action may remain continuous across a five-minute boundary. Its original signal candle remains attached to the eventual order, matching the comparison backtest behavior.

## Cycle Ordering

Every unattended cycle keeps this priority:

1. Reconcile a persisted pending order and return.
2. Return immediately for `emergency_halt`.
3. Validate balances and current orderbook data.
4. Evaluate completed-candle crash protection.
5. If risk is pending or confirmed, clear normal RSI confirmation and handle risk before any RSI order.
6. Calculate provisional RSI and update the 30-second confirmation state.
7. Submit a mature normal action only when minimum-order validation passes.

No blocking `sleep(30)` is introduced. The existing 10-second service loop remains responsive to emergency risk and pending orders.

## Order And Restart Safety

Before creating a pending order, the normal confirmation fields are cleared. The order identifier is still persisted before submission, and ambiguous submissions are still reconciled by identifier or UUID. A completed or partially filled-and-cancelled order advances the phase and records the consumed signal candle.

If a mature action is below Upbit's minimum order, the signal candle is consumed and the confirmation is cleared so the service does not repeat the same rejected decision every ten seconds.

Persisting the confirmation allows normal short process interruptions to retain progress, while the 20-second observation-gap rule prevents a restart or outage from converting an unobserved interval into a mature signal.

## Status And Operations

While a valid condition is accumulating time, `run_auto_cycle` returns `confirming` with the provisional RSI and no action. Existing `waiting`, `dry_run`, order, error, emergency, and halt statuses remain. Logs therefore show when the bot is waiting for the 30-second requirement without adding a new Telegram message type.

AWS deployment continues to use the existing installer and systemd unit. Deployment instructions must require stopping the service, backing up the state file, pulling the branch, installing, running one dry-run cycle, and only then restarting live mode.

## Tests

Automated tests must prove:

- legacy state JSON loads with empty confirmation fields and new state round-trips;
- a candidate does not trade before 30 seconds and trades after 30 seconds;
- threshold loss, action change, observation gap, stale data, and emergency risk reset confirmation;
- confirmation can continue across a five-minute boundary;
- only one normal action is consumed for its signal candle;
- minimum-order rejection clears and consumes the mature signal;
- pending-order reconciliation and emergency priority remain unchanged;
- dry-run never calls an order endpoint;
- the complete project test suite passes.

## Pull Request

The current `codex/upbit-rsi-sell-bot` branch will be pushed to `origin` after verification. A draft pull request will target the repository's default branch and describe the live strategy change, the supporting 90-day comparison, migration behavior, safety ordering, and test evidence.
