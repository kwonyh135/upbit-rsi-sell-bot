# KRW-HUNT Intrabar RSI Timing Study

## Coverage

- Market: `KRW-HUNT`
- First observed second: `2026-04-02T13:21:48+00:00`
- Last observed second: `2026-07-01T12:48:06+00:00`
- Observed trade seconds: `63719`
- Coverage days: `89.97659722222222222222222222`
- Missing trade seconds: `7710260`
- Chronological split: `2026-06-01T12:59:20+00:00`

## Recommendation

Recommendation: **hold_30s**

Reason: holdout return, MDD, and 0.30% slippage criteria passed.

Protected and unprotected rows are identical across all splits because every run recorded `0` emergency exits, so the crash-protection branch never changed execution; this is not caused by missing configuration.

## Full Period (18 runs)

| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| protected | completed | 0.05% | 0.05% | 29.37% | 20.20% | 406 | 0 | 0 | 308045 KRW | 308044 KRW |
| protected | hold_30s | 0.05% | 0.05% | 55.83% | 21.57% | 459 | 113 | 0 | 364667 KRW | 364666 KRW |
| protected | immediate | 0.05% | 0.05% | 26.19% | 23.54% | 536 | 213 | 0 | 380172 KRW | 380171 KRW |
| protected | completed | 0.05% | 0.30% | -16.75% | 26.62% | 406 | 0 | 0 | 247238 KRW | 1483416 KRW |
| protected | hold_30s | 0.05% | 0.30% | -3.80% | 26.65% | 459 | 113 | 0 | 285284 KRW | 1711694 KRW |
| protected | immediate | 0.05% | 0.30% | -27.90% | 39.49% | 536 | 213 | 0 | 289722 KRW | 1738322 KRW |
| protected | completed | 0.05% | 1.00% | -75.71% | 75.95% | 406 | 0 | 0 | 145299 KRW | 2905979 KRW |
| protected | hold_30s | 0.05% | 1.00% | -74.99% | 75.48% | 459 | 113 | 0 | 158923 KRW | 3178489 KRW |
| protected | immediate | 0.05% | 1.00% | -84.90% | 85.03% | 536 | 213 | 0 | 154778 KRW | 3095587 KRW |
| unprotected | completed | 0.05% | 0.05% | 29.37% | 20.20% | 406 | 0 | 0 | 308045 KRW | 308044 KRW |
| unprotected | hold_30s | 0.05% | 0.05% | 55.83% | 21.57% | 459 | 113 | 0 | 364667 KRW | 364666 KRW |
| unprotected | immediate | 0.05% | 0.05% | 26.19% | 23.54% | 536 | 213 | 0 | 380172 KRW | 380171 KRW |
| unprotected | completed | 0.05% | 0.30% | -16.75% | 26.62% | 406 | 0 | 0 | 247238 KRW | 1483416 KRW |
| unprotected | hold_30s | 0.05% | 0.30% | -3.80% | 26.65% | 459 | 113 | 0 | 285284 KRW | 1711694 KRW |
| unprotected | immediate | 0.05% | 0.30% | -27.90% | 39.49% | 536 | 213 | 0 | 289722 KRW | 1738322 KRW |
| unprotected | completed | 0.05% | 1.00% | -75.71% | 75.95% | 406 | 0 | 0 | 145299 KRW | 2905979 KRW |
| unprotected | hold_30s | 0.05% | 1.00% | -74.99% | 75.48% | 459 | 113 | 0 | 158923 KRW | 3178489 KRW |
| unprotected | immediate | 0.05% | 1.00% | -84.90% | 85.03% | 536 | 213 | 0 | 154778 KRW | 3095587 KRW |

## Training (18 runs)

| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| protected | completed | 0.05% | 0.05% | 17.04% | 11.76% | 251 | 0 | 0 | 188718 KRW | 188717 KRW |
| protected | hold_30s | 0.05% | 0.05% | 24.28% | 13.67% | 283 | 66 | 0 | 217299 KRW | 217298 KRW |
| protected | immediate | 0.05% | 0.05% | 13.48% | 12.29% | 338 | 133 | 0 | 240966 KRW | 240966 KRW |
| protected | completed | 0.05% | 0.30% | -11.13% | 16.46% | 251 | 0 | 0 | 163983 KRW | 983894 KRW |
| protected | hold_30s | 0.05% | 0.30% | -8.09% | 16.14% | 283 | 66 | 0 | 186144 KRW | 1116863 KRW |
| protected | immediate | 0.05% | 0.30% | -20.47% | 27.07% | 338 | 133 | 0 | 201855 KRW | 1211124 KRW |
| protected | completed | 0.05% | 1.00% | -58.82% | 59.70% | 251 | 0 | 0 | 114467 KRW | 2289340 KRW |
| protected | hold_30s | 0.05% | 1.00% | -60.44% | 61.65% | 283 | 66 | 0 | 125674 KRW | 2513512 KRW |
| protected | immediate | 0.05% | 1.00% | -70.54% | 71.12% | 338 | 133 | 0 | 130010 KRW | 2600211 KRW |
| unprotected | completed | 0.05% | 0.05% | 17.04% | 11.76% | 251 | 0 | 0 | 188718 KRW | 188717 KRW |
| unprotected | hold_30s | 0.05% | 0.05% | 24.28% | 13.67% | 283 | 66 | 0 | 217299 KRW | 217298 KRW |
| unprotected | immediate | 0.05% | 0.05% | 13.48% | 12.29% | 338 | 133 | 0 | 240966 KRW | 240966 KRW |
| unprotected | completed | 0.05% | 0.30% | -11.13% | 16.46% | 251 | 0 | 0 | 163983 KRW | 983894 KRW |
| unprotected | hold_30s | 0.05% | 0.30% | -8.09% | 16.14% | 283 | 66 | 0 | 186144 KRW | 1116863 KRW |
| unprotected | immediate | 0.05% | 0.30% | -20.47% | 27.07% | 338 | 133 | 0 | 201855 KRW | 1211124 KRW |
| unprotected | completed | 0.05% | 1.00% | -58.82% | 59.70% | 251 | 0 | 0 | 114467 KRW | 2289340 KRW |
| unprotected | hold_30s | 0.05% | 1.00% | -60.44% | 61.65% | 283 | 66 | 0 | 125674 KRW | 2513512 KRW |
| unprotected | immediate | 0.05% | 1.00% | -70.54% | 71.12% | 338 | 133 | 0 | 130010 KRW | 2600211 KRW |

## Holdout (18 runs)

| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| protected | completed | 0.05% | 0.05% | 10.26% | 15.02% | 155 | 0 | 0 | 102074 KRW | 102073 KRW |
| protected | hold_30s | 0.05% | 0.05% | 25.07% | 15.49% | 176 | 47 | 0 | 118652 KRW | 118652 KRW |
| protected | immediate | 0.05% | 0.05% | 10.92% | 17.57% | 198 | 80 | 0 | 122732 KRW | 122732 KRW |
| protected | completed | 0.05% | 0.30% | -6.61% | 16.34% | 155 | 0 | 0 | 93764 KRW | 562565 KRW |
| protected | hold_30s | 0.05% | 0.30% | 4.35% | 16.34% | 176 | 47 | 0 | 107910 KRW | 647442 KRW |
| protected | immediate | 0.05% | 0.30% | -9.62% | 19.93% | 198 | 80 | 0 | 110512 KRW | 663053 KRW |
| protected | completed | 0.05% | 1.00% | -41.29% | 42.11% | 155 | 0 | 0 | 74887 KRW | 1497589 KRW |
| protected | hold_30s | 0.05% | 1.00% | -37.09% | 37.62% | 176 | 47 | 0 | 84024 KRW | 1680362 KRW |
| protected | immediate | 0.05% | 1.00% | -49.01% | 49.44% | 198 | 80 | 0 | 84044 KRW | 1680754 KRW |
| unprotected | completed | 0.05% | 0.05% | 10.26% | 15.02% | 155 | 0 | 0 | 102074 KRW | 102073 KRW |
| unprotected | hold_30s | 0.05% | 0.05% | 25.07% | 15.49% | 176 | 47 | 0 | 118652 KRW | 118652 KRW |
| unprotected | immediate | 0.05% | 0.05% | 10.92% | 17.57% | 198 | 80 | 0 | 122732 KRW | 122732 KRW |
| unprotected | completed | 0.05% | 0.30% | -6.61% | 16.34% | 155 | 0 | 0 | 93764 KRW | 562565 KRW |
| unprotected | hold_30s | 0.05% | 0.30% | 4.35% | 16.34% | 176 | 47 | 0 | 107910 KRW | 647442 KRW |
| unprotected | immediate | 0.05% | 0.30% | -9.62% | 19.93% | 198 | 80 | 0 | 110512 KRW | 663053 KRW |
| unprotected | completed | 0.05% | 1.00% | -41.29% | 42.11% | 155 | 0 | 0 | 74887 KRW | 1497589 KRW |
| unprotected | hold_30s | 0.05% | 1.00% | -37.09% | 37.62% | 176 | 47 | 0 | 84024 KRW | 1680362 KRW |
| unprotected | immediate | 0.05% | 1.00% | -49.01% | 49.44% | 198 | 80 | 0 | 84044 KRW | 1680754 KRW |

## Cycle Concentration

- completed: Completed cycles: `170`; busiest UTC day 2026-06-30 held 12/406 events (2.96%)
- immediate: Completed cycles: `228`; busiest UTC day 2026-06-29 held 19/536 events (3.54%)
- hold_30s: Completed cycles: `192`; busiest UTC day 2026-06-29 held 14/459 events (3.05%)

## Event-Level Differences

- immediate vs completed: 529 unique events; 399 completed-mode events absent.
- hold_30s vs completed: 459 unique events; 406 completed-mode events absent.

## Limitations

- Missing trade seconds are periods without observed trades, not reconstructed prices.
- Signals fill at the next observed trade with fixed adverse slippage and a 0.05% fee.
- Training and holdout restart from KRW 3,000,000 and do not continue full-period portfolio state.
- Historical results do not guarantee future performance or available market liquidity.
- This study does not change live commands, runtime state, or place orders.
