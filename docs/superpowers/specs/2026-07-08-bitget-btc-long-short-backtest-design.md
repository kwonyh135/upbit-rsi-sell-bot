# Bitget BTC Long/Short Backtest Design

## Objective

Evaluate whether the existing RSI split-entry strategy remains useful on Bitcoin when traded as a Bitget USDT-margined perpetual future. Compare long-only, short-only, and bidirectional variants over the latest six complete months of five-minute candles, then produce a Korean HTML report.

This work is research-only. It must not change the KRW-HUNT live bot, its state, AWS service, or order code.

## Market And Portfolio Assumptions

- Venue: Bitget
- Instrument: `BTCUSDT` USDT-M perpetual futures
- Candle interval: completed five-minute candles
- Test window: latest six complete months available at execution time
- Warm-up: enough earlier data to initialize RSI and the four-hour regime indicators
- Starting equity: 3,000 USDT
- Position mode: one-way; never hold long and short simultaneously
- Leverage: isolated 1x for both long and short
- Maximum exposure: 100% of current equity
- Liquidation is not expected at 1x, but equity must never be allowed below zero in the simulator

## Data

Download public five-minute contract candles from Bitget's historical contract API and historical funding settlements from the funding-rate API. Cache raw responses locally so reruns use identical inputs.

Validation rules:

- Sort timestamps and reject duplicates with conflicting OHLC values.
- Record missing five-minute intervals and API gaps in the report.
- Exclude the current incomplete candle.
- Require six complete test months; fail clearly rather than silently shortening the study.
- Preserve timestamps in UTC and display both UTC and Asia/Seoul dates in the report.

## Signal Rules

Use RSI 14 calculated from completed five-minute closes.

### Long

- Enter half exposure when RSI is at or below 45.
- Increase to full exposure when RSI is at or below 40.
- Reduce by half when RSI is at or above 60.
- Close the remainder when RSI is at or above 65.

### Short

- Enter half short exposure when RSI is at or above 60.
- Increase to full short exposure when RSI is at or above 65.
- Reduce by half when RSI is at or below 45.
- Close the remainder when RSI is at or below 40.

All signals fill at the next five-minute candle open. This avoids look-ahead bias. The six-month five-minute dataset cannot reproduce the live HUNT bot's 30-second intrabar confirmation, so that behavior is explicitly outside this study.

When a close signal and an opposite entry are both eligible, close the current position first. The opposite position may open no earlier than the next completed signal candle, preventing an implicit same-bar reversal and double execution ambiguity.

## Market Regime

Build four-hour candles only from five-minute candles already available at each point. Use four-hour EMA 50 and EMA 200 without future data.

- Bull regime: close is above EMA 200 and EMA 50 is above EMA 200.
- Bear regime: close is below EMA 200 and EMA 50 is below EMA 200.
- Neutral regime: all other states.

Regime labels serve two purposes:

1. Break down every strategy's results into bull, bear, and neutral periods.
2. Define a filtered bidirectional strategy that permits new longs only in bull regimes, new shorts only in bear regimes, and no new position in neutral regimes. Existing positions continue to follow RSI exits.

## Strategies Compared

1. Cash benchmark.
2. BTC buy-and-hold benchmark at 1x exposure.
3. Long-only RSI strategy.
4. Short-only RSI strategy.
5. Unfiltered bidirectional RSI strategy.
6. Regime-filtered bidirectional RSI strategy.

The fixed HUNT thresholds are the primary experiment. A small sensitivity study may vary each paired boundary by at most five RSI points, but it must not replace the fixed-rule result or search a broad parameter grid.

## Costs And Accounting

- Base execution fee: 0.06% taker fee per fill.
- Base adverse slippage: 0.02% per fill.
- Stress slippage scenarios: 0.05% and 0.10% per fill.
- Apply each historical funding settlement only when a position is open at its timestamp.
- Positive funding means longs pay shorts; negative funding means shorts pay longs.
- Size each half or full target from current equity, not original capital.
- Mark open positions to each candle close for equity and drawdown calculations.

Report transaction fees, slippage, and funding separately. Do not assume maker execution or fee discounts.

## Validation

Use the first four chronological months as the development segment and the final two months as untouched holdout. Fixed-rule results are reported on both segments and the full period.

If sensitivity variants are evaluated, select them using only the development segment and evaluate the selected variant once on holdout. The report must flag a result as unstable when it has any of these traits:

- Negative holdout return after base costs.
- Holdout maximum drawdown above 20%.
- Negative return under 0.05% slippage stress.
- Fewer than ten completed position cycles in holdout.
- More than half of total profit comes from one completed cycle.
- It underperforms buy-and-hold while taking comparable or greater drawdown.

Historical results do not establish future profitability. The conclusion must be `recommended for further paper trading`, `inconclusive`, or `not recommended`; it must not recommend immediate live deployment.

## Metrics

For every strategy and cost scenario, calculate:

- Total and annualized return
- Ending equity
- Maximum drawdown
- Trade fills and completed position cycles
- Win rate, profit factor, average win, and average loss
- Long and short contribution
- Transaction fee, slippage, and funding totals
- Time in market and turnover
- Bull, bear, and neutral regime return contribution
- Best and worst completed cycle
- Profit concentration

## Outputs

Generate:

- Cached raw Bitget candle and funding data under a BTC-specific research directory.
- Machine-readable result files for reproducibility.
- `docs/bitget-btc-long-short-backtest-latest.md` as a concise result summary.
- `docs/bitget-btc-long-short-backtest-latest.html` as the primary Korean report.

The HTML report must include an executive conclusion, data quality section, assumptions, strategy diagrams or tables, equity and drawdown charts, regime shading or regime tables, cost breakdowns, development-versus-holdout results, and limitations. It must open locally without a server or external JavaScript dependency.

## Isolation And Safety

- Use public Bitget market endpoints only; no API key is required.
- Do not submit orders or add Bitget live-trading commands.
- Keep all BTC research state and files separate from KRW-HUNT runtime state.
- Do not read, print, or modify `.env` secrets.
- Do not deploy anything to AWS as part of this study.

## Tests And Acceptance

Automated tests must cover long and short P&L signs, split sizing, next-open execution, reversal delay, funding direction, fee and slippage accounting, regime classification without look-ahead, holdout separation, and missing-data validation.

The study is complete when:

1. Six complete months of validated Bitget data are cached.
2. All six strategies run under base and stress costs.
3. Development, holdout, full-period, and regime results are present.
4. Automated tests pass.
5. The Markdown and standalone Korean HTML reports are generated and visually checked.
6. No HUNT live-trading file or runtime state is changed.
