# KRW-HUNT Intrabar RSI Timing Study

## Coverage

- Market: `KRW-HUNT`
- First observed second: `2026-04-02T22:13:11+00:00`
- Last observed second: `2026-07-01T21:56:26+00:00`
- Observed trade seconds: `63778`
- Coverage days: `89.98836805555555555555555556`
- Missing trade seconds: `7711218`
- Chronological split: `2026-06-01T22:02:01+00:00`

## Recommendation

Recommendation: **hold_30s**

Reason: holdout return, MDD, and 0.30% slippage criteria passed.

## Full Period (18 runs)

| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| protected | completed | 0.05% | 0.05% | 32.01% | 24.12% | 406 | 0 | 0 | 320809 KRW | 320809 KRW |
| protected | hold_30s | 0.05% | 0.05% | 59.75% | 23.56% | 459 | 113 | 0 | 364667 KRW | 364666 KRW |
| protected | immediate | 0.05% | 0.05% | 29.78% | 25.65% | 534 | 212 | 0 | 380601 KRW | 380600 KRW |
| protected | completed | 0.05% | 0.30% | -15.04% | 29.17% | 406 | 0 | 0 | 257360 KRW | 1544149 KRW |
| protected | hold_30s | 0.05% | 0.30% | -1.37% | 30.89% | 459 | 113 | 0 | 285284 KRW | 1711694 KRW |
| protected | immediate | 0.05% | 0.30% | -25.76% | 41.50% | 534 | 212 | 0 | 290233 KRW | 1741391 KRW |
| protected | completed | 0.05% | 1.00% | -75.20% | 76.25% | 406 | 0 | 0 | 150813 KRW | 3016269 KRW |
| protected | hold_30s | 0.05% | 1.00% | -74.36% | 75.48% | 459 | 113 | 0 | 158923 KRW | 3178489 KRW |
| protected | immediate | 0.05% | 1.00% | -84.40% | 85.02% | 534 | 212 | 0 | 155243 KRW | 3104892 KRW |
| unprotected | completed | 0.05% | 0.05% | 32.01% | 24.12% | 406 | 0 | 0 | 320809 KRW | 320809 KRW |
| unprotected | hold_30s | 0.05% | 0.05% | 59.75% | 23.56% | 459 | 113 | 0 | 364667 KRW | 364666 KRW |
| unprotected | immediate | 0.05% | 0.05% | 29.78% | 25.65% | 534 | 212 | 0 | 380601 KRW | 380600 KRW |
| unprotected | completed | 0.05% | 0.30% | -15.04% | 29.17% | 406 | 0 | 0 | 257360 KRW | 1544149 KRW |
| unprotected | hold_30s | 0.05% | 0.30% | -1.37% | 30.89% | 459 | 113 | 0 | 285284 KRW | 1711694 KRW |
| unprotected | immediate | 0.05% | 0.30% | -25.76% | 41.50% | 534 | 212 | 0 | 290233 KRW | 1741391 KRW |
| unprotected | completed | 0.05% | 1.00% | -75.20% | 76.25% | 406 | 0 | 0 | 150813 KRW | 3016269 KRW |
| unprotected | hold_30s | 0.05% | 1.00% | -74.36% | 75.48% | 459 | 113 | 0 | 158923 KRW | 3178489 KRW |
| unprotected | immediate | 0.05% | 1.00% | -84.40% | 85.02% | 534 | 212 | 0 | 155243 KRW | 3104892 KRW |

## Training (18 runs)

| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| protected | completed | 0.05% | 0.05% | 26.18% | 13.36% | 253 | 0 | 0 | 198418 KRW | 198418 KRW |
| protected | hold_30s | 0.05% | 0.05% | 25.10% | 14.31% | 285 | 66 | 0 | 218470 KRW | 218470 KRW |
| protected | immediate | 0.05% | 0.05% | 14.58% | 13.13% | 338 | 132 | 0 | 242035 KRW | 242035 KRW |
| protected | completed | 0.05% | 0.30% | -4.34% | 15.72% | 253 | 0 | 0 | 171946 KRW | 1031675 KRW |
| protected | hold_30s | 0.05% | 0.30% | -7.64% | 19.28% | 285 | 66 | 0 | 187009 KRW | 1122054 KRW |
| protected | immediate | 0.05% | 0.30% | -19.72% | 28.71% | 338 | 132 | 0 | 202734 KRW | 1216400 KRW |
| protected | completed | 0.05% | 1.00% | -55.87% | 57.20% | 253 | 0 | 0 | 119168 KRW | 2383396 KRW |
| protected | hold_30s | 0.05% | 1.00% | -60.42% | 61.65% | 285 | 66 | 0 | 126044 KRW | 2520923 KRW |
| protected | immediate | 0.05% | 1.00% | -70.29% | 71.09% | 338 | 132 | 0 | 130558 KRW | 2611183 KRW |
| unprotected | completed | 0.05% | 0.05% | 26.18% | 13.36% | 253 | 0 | 0 | 198418 KRW | 198418 KRW |
| unprotected | hold_30s | 0.05% | 0.05% | 25.10% | 14.31% | 285 | 66 | 0 | 218470 KRW | 218470 KRW |
| unprotected | immediate | 0.05% | 0.05% | 14.58% | 13.13% | 338 | 132 | 0 | 242035 KRW | 242035 KRW |
| unprotected | completed | 0.05% | 0.30% | -4.34% | 15.72% | 253 | 0 | 0 | 171946 KRW | 1031675 KRW |
| unprotected | hold_30s | 0.05% | 0.30% | -7.64% | 19.28% | 285 | 66 | 0 | 187009 KRW | 1122054 KRW |
| unprotected | immediate | 0.05% | 0.30% | -19.72% | 28.71% | 338 | 132 | 0 | 202734 KRW | 1216400 KRW |
| unprotected | completed | 0.05% | 1.00% | -55.87% | 57.20% | 253 | 0 | 0 | 119168 KRW | 2383396 KRW |
| unprotected | hold_30s | 0.05% | 1.00% | -60.42% | 61.65% | 285 | 66 | 0 | 126044 KRW | 2520923 KRW |
| unprotected | immediate | 0.05% | 1.00% | -70.29% | 71.09% | 338 | 132 | 0 | 130558 KRW | 2611183 KRW |

## Holdout (18 runs)

| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| protected | completed | 0.05% | 0.05% | 3.45% | 18.05% | 148 | 0 | 0 | 92751 KRW | 92751 KRW |
| protected | hold_30s | 0.05% | 0.05% | 25.68% | 18.21% | 168 | 46 | 0 | 111851 KRW | 111851 KRW |
| protected | immediate | 0.05% | 0.05% | 12.64% | 20.22% | 190 | 78 | 0 | 117097 KRW | 117097 KRW |
| protected | completed | 0.05% | 0.30% | -11.71% | 19.64% | 148 | 0 | 0 | 85595 KRW | 513547 KRW |
| protected | hold_30s | 0.05% | 0.30% | 5.64% | 19.03% | 168 | 46 | 0 | 102106 KRW | 612614 KRW |
| protected | immediate | 0.05% | 0.30% | -7.53% | 21.37% | 190 | 78 | 0 | 105803 KRW | 634797 KRW |
| protected | completed | 0.05% | 1.00% | -43.30% | 45.35% | 148 | 0 | 0 | 69167 KRW | 1383185 KRW |
| protected | hold_30s | 0.05% | 1.00% | -34.96% | 37.20% | 168 | 46 | 0 | 80237 KRW | 1604602 KRW |
| protected | immediate | 0.05% | 1.00% | -46.72% | 48.56% | 190 | 78 | 0 | 81124 KRW | 1622349 KRW |
| unprotected | completed | 0.05% | 0.05% | 3.45% | 18.05% | 148 | 0 | 0 | 92751 KRW | 92751 KRW |
| unprotected | hold_30s | 0.05% | 0.05% | 25.68% | 18.21% | 168 | 46 | 0 | 111851 KRW | 111851 KRW |
| unprotected | immediate | 0.05% | 0.05% | 12.64% | 20.22% | 190 | 78 | 0 | 117097 KRW | 117097 KRW |
| unprotected | completed | 0.05% | 0.30% | -11.71% | 19.64% | 148 | 0 | 0 | 85595 KRW | 513547 KRW |
| unprotected | hold_30s | 0.05% | 0.30% | 5.64% | 19.03% | 168 | 46 | 0 | 102106 KRW | 612614 KRW |
| unprotected | immediate | 0.05% | 0.30% | -7.53% | 21.37% | 190 | 78 | 0 | 105803 KRW | 634797 KRW |
| unprotected | completed | 0.05% | 1.00% | -43.30% | 45.35% | 148 | 0 | 0 | 69167 KRW | 1383185 KRW |
| unprotected | hold_30s | 0.05% | 1.00% | -34.96% | 37.20% | 168 | 46 | 0 | 80237 KRW | 1604602 KRW |
| unprotected | immediate | 0.05% | 1.00% | -46.72% | 48.56% | 190 | 78 | 0 | 81124 KRW | 1622349 KRW |

## Cycle Concentration

- completed: Completed cycles: `67`; best cycle P&L 265562 KRW (9.88% of positive P&L); worst cycle P&L -328101 KRW
- immediate: Completed cycles: `82`; best cycle P&L 230689 KRW (8.28% of positive P&L); worst cycle P&L -372215 KRW
- hold_30s: Completed cycles: `69`; best cycle P&L 398492 KRW (11.17% of positive P&L); worst cycle P&L -356845 KRW

## Event-Level Differences

- immediate vs completed: 268 matched candle/action events; mean signal lead 147.56s; 266 mode-only; 138 completed-only.
- hold_30s vs completed: 301 matched candle/action events; mean signal lead 114.73s; 158 mode-only; 105 completed-only.

## Limitations

- Missing trade seconds are periods without observed trades, not reconstructed prices.
- Completed-candle and emergency signals fill on the first boundary-or-later trade.
- Intrabar signals fill on the next strictly later observed trade with fixed adverse slippage and a 0.05% fee.
- Training and holdout restart from KRW 3,000,000 and do not continue full-period portfolio state.
- Historical results do not guarantee future performance or available market liquidity.
- This study does not change live commands, runtime state, or place orders.
