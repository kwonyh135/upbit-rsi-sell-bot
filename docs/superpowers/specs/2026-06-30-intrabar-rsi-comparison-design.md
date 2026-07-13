# Intrabar RSI Timing Comparison Design

## Objective

Determine whether KRW-HUNT RSI orders should use completed five-minute candles,
the first intrabar threshold crossing, or a threshold that remains true for 30
seconds. The comparison must avoid look-ahead bias and must not alter or place
orders through the live AWS bot.

## Strategies

All variants use RSI period 14 and the production phase rules:

- `buy_1`: RSI at or below 45, spend half the available KRW.
- `buy_2`: RSI at or below 40, spend the remaining fee-safe KRW.
- `sell_1`: RSI at or above 60, sell half the available HUNT unless already in
  `sell_2`.
- `sell_2`: RSI at or above 65, sell all available HUNT.

The variants differ only in signal timing:

1. **Completed five-minute candle**: calculate RSI after the five-minute candle
   closes and execute at the next observable trade price.
2. **Intrabar immediate**: calculate provisional RSI from the latest price as
   the unfinished five-minute close and signal on the first threshold crossing.
3. **Intrabar 30-second hold**: use the same provisional RSI, but signal only
   after the applicable condition remains true for 30 consecutive wall-clock
   seconds.

Only one normal RSI action may be generated from a five-minute candle. A filled
action advances the same phase state used by production.

## Data

The primary study uses the latest available three months of public KRW-HUNT
second candles. The downloader will:

- request data in reverse chronological pages and rate-limit requests;
- save progress to a local CSV so interrupted downloads can resume;
- deduplicate by timestamp and sort chronologically;
- record the actual covered interval and missing-trade seconds;
- never use authenticated account or order endpoints.

Second candles exist only when a trade occurs. Signal evaluation therefore uses
a one-second clock with the last observed trade price carried forward. An order
can execute only at the next observed trade, preventing synthetic fills during
periods with no market activity.

The completed-candle control is aggregated from the same second-candle dataset,
so all three variants share identical market coverage. The aggregate is checked
against a sample from Upbit's five-minute REST candles.

## RSI And Execution Model

At each point in time, RSI uses only information already available:

- all prior completed five-minute closes; and
- for intrabar variants, the latest observed price as the current unfinished
  candle close.

Signals execute on the next observable trade, never at the price that created
the signal. Normal orders apply a 0.05% fee and 0.05% adverse slippage. Stress
runs apply 0.30% and 1.00% adverse slippage. Buy prices increase by slippage and
sell prices decrease by slippage.

The initial portfolio is KRW 3,000,000 with no HUNT, matching the existing crash
study. Portfolio state, average purchase price, and split-order phases are
updated after every simulated fill.

## Crash Protection

The primary comparison holds the current production protection constant across
all variants:

- completed five-minute high-to-close drop at or above 6%; or
- average-purchase-price loss at or above 12%;
- confirmation on two consecutive completed five-minute candles.

The existing immediate manual-unlock proxy is used after an emergency exit so
operator response time does not favor one RSI timing variant. A secondary run
without crash protection isolates the effect of RSI timing itself.

## Evaluation

Report full-period results and a chronological two-thirds/one-third split. For
each strategy and slippage scenario, report:

- net return and final portfolio value;
- maximum drawdown;
- number of completed orders and full buy/sell cycles;
- fees and modeled slippage paid;
- false intrabar signals, defined as intrabar actions whose condition is no
  longer true at that five-minute candle's close;
- emergency exits;
- contribution of the best and worst trade cycles.

The intrabar approach is considered preferable only if its holdout net return is
higher than the completed-candle control, its maximum drawdown is not materially
worse, and the advantage remains under 0.30% slippage. A result driven by one
trade cycle or lost under modest slippage is reported as inconclusive.

## Outputs

- Resumable second-candle CSV under `data/backtests/`.
- Machine-readable comparison JSON under `data/backtests/`.
- Markdown report under `docs/` containing assumptions, coverage, metrics,
  event-level differences, limitations, and a recommendation.
- Focused unit tests for provisional RSI, 30-second confirmation, next-trade
  execution, missing-trade intervals, and no-look-ahead behavior.

## Safety And Limitations

- The study uses public quotation endpoints only and cannot place orders.
- Historical trade prices do not contain the full order book, so slippage stress
  tests bound rather than reproduce actual fills.
- Carry-forward prices model signal continuity, not guaranteed execution.
- Three months may contain too few complete strategy cycles for a decisive
  result; in that case the recommendation remains completed-candle execution
  while a prospective shadow recorder gathers more data.
- Historical results do not guarantee future performance.
