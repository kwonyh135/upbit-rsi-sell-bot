# Crash Protection Backtest Design

## Goal

Use the latest available six months of KRW-HUNT five-minute candles to compare
three crash-protection families on top of the production RSI 60/65 sell and
45/40 buy rules. Recommend a balanced configuration that reduces drawdown
without materially destroying validated return.

This research does not change the live AWS trading rules. Live behavior will
be changed only after the backtest report is reviewed and one configuration is
explicitly approved.

## Data and Reproducibility

- Fetch public KRW-HUNT five-minute candles from Upbit through the last fully
  completed candle at command start.
- Request 264 pages of 200 candles, deduplicate timestamps, and retain the most
  recent 183 calendar days.
- Persist the fetched candles and metadata outside Git under
  `data/backtests/` so the report can be reproduced exactly.
- Record the first timestamp, last timestamp, candle count, missing intervals,
  download time, and market in the report.
- Rate-limit paginated requests so the public API is not sent a burst of 264
  calls.

Five-minute OHLC data cannot reconstruct the current live bot's two 10-second
observations. The primary test therefore confirms risk only at completed candle
closes and executes at the next candle open. A secondary low-touch sensitivity
run treats the candle low as a possible live trigger but still executes at the
next open. The primary close-confirmed result determines ranking.

## Shared Portfolio Model

- Start with KRW 3,000,000 fully invested in HUNT at the first execution price,
  matching the existing split-buyback backtest.
- Reproduce the production phase behavior, including broad RSI sells and the
  rule that `buy_2` cannot repeat `buy_1` between RSI 40 and 45.
- Calculate RSI from completed candles only. A signal is filled at the next
  candle open to avoid look-ahead bias.
- Apply 0.05% fee and 0.05% normal slippage to every trade.
- Re-run crash exits with 0.30% and 1.00% slippage as stress tests.
- Track weighted average buy price after every purchase.

The no-protection production strategy and the existing fixed 7% rolling-high
or 10% average-loss rule are both included as reference baselines.

## Protection Family A: Fixed Threshold Full Exit

Confirm risk when either a rolling-high drawdown or average-buy-price loss
crosses a fixed threshold for consecutive completed candles. Sell all HUNT on
the next candle open.

Search a bounded grid over rolling windows of 5, 15, and 30 minutes; rolling
drawdowns from 5% through 10%; average losses of 8%, 10%, 12%, and 15%; and one,
two, or three confirmations. This family is simple to audit and is closest to
the current live behavior, but it can overreact when normal volatility rises.

## Protection Family B: ATR-Adaptive Full Exit

Calculate 14-period ATR on completed five-minute candles. The rolling-high and
average-loss limits are the greater of a fixed floor and a configured ATR
multiple. Confirm on completed candles and sell all HUNT at the next open.

Search small grids for 3%-6% rolling floors, 8%-12% average-loss floors, ATR
multiples from 2.0 through 4.0, and one or two confirmations. This family adapts
to changing volatility but has more parameters and therefore receives a
stricter robustness check.

## Protection Family C: Two-Stage Defense

Sell 50% on an initial warning and sell the remainder only when a stronger
threshold or continued weakness is confirmed. The first warning searches
rolling drops of 4%-7% and average losses of 7%-10%. The final exit searches an
additional 2%-4% decline or one to three further bearish closes.

This family limits damage while preserving some exposure to immediate
rebounds. Its trade count, fees, and residual loss after the first exit are
reported explicitly.

## Recovery Modes

Every protection configuration is evaluated with both recovery classes.

Manual recovery is represented by deterministic waits of 6, 24, and 72 hours.
After the wait the halt is cleared to `buy_1`; the existing RSI rules decide
when to buy. A permanent halt is retained as a reference, not as a recommended
operating mode.

Automatic recovery requires all of the following before clearing to `buy_1`:

- A minimum cooldown selected from 1, 3, or 6 hours.
- No active crash condition for 3, 6, or 12 consecutive five-minute candles.
- Close above EMA20 and RSI at or above 45.

The recovery rule does not itself place a buy. It only re-enables the existing
RSI strategy, preventing the protection layer from inventing a new entry rule.

## Validation and Ranking

Use the first four chronological months for parameter selection and reserve the
last two months for validation. Full-period results are descriptive only and
cannot select the winner.

Report return, maximum drawdown, return-to-drawdown ratio, emergency exits,
normal trades, time held in cash, peak-recovery duration, and false exits. A
false exit means price trades at least 5% above the crash exit within 24 hours
without first falling another 5%.

A candidate is balanced-eligible when validation return is at least 90% of the
no-protection validation return. Among eligible candidates, prefer the lowest
validation maximum drawdown, then the higher return-to-drawdown ratio. Reject a
winner that collapses under adjacent parameter values or the 0.30% crash-exit
slippage test. The final report presents one recommended configuration and the
best configuration from each of the three families.

## Implementation Boundaries

- Add a dedicated crash backtest module rather than complicating the live
  trader or the existing simple backtests.
- Add a CLI command that downloads or reuses an exact candle snapshot, runs the
  study, and writes machine-readable results plus a concise Markdown report.
- Cover signal timing, phase transitions, costs, all recovery modes, metrics,
  chronological split, and ranking with deterministic tests.
- Do not read private API credentials and do not call any order endpoint.
