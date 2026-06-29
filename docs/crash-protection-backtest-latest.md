# KRW-HUNT Crash Protection Backtest

## Data

- Market: `KRW-HUNT`
- First candle: `2025-12-28T00:30:00+00:00`
- Last candle: `2026-06-29T00:20:00+00:00`
- Candle count: `26117`
- Missing five-minute intervals: `26586`

## Recommendation

- Meets 90% validation-return requirement: **yes**
- Protection: **Fixed threshold** (`fixed-w1-d6-l12-c2`)
- Recovery: **manual-6h**
- Validation return: **16.44%**
- Validation MDD: **21.92%**
- Full-period return: **66.02%**
- Full-period MDD: **21.92%**
- Emergency exits: **3**

## Baselines

| Strategy | Return | MDD | Emergency exits |
| --- | ---: | ---: | ---: |
| No protection baseline | 56.25% | 26.98% | 0 |
| Current 7%/10% permanent halt reference | 1.99% | 14.46% | 1 |

## Family Winners

| Family | Recovery | Eligible | Validation Return | Validation MDD | Validation exits | Full Return | Full MDD | Emergency exits | False exits |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed threshold | manual-6h | yes | 16.44% | 21.92% | 0 | 66.02% | 21.92% | 3 | 1 |
| ATR adaptive | manual-24h | no | 5.21% | 15.29% | 7 | 76.21% | 17.32% | 21 | 8 |
| Two-stage defense | auto-3h | no | -0.39% | 22.72% | 7 | 56.25% | 22.72% | 22 | 8 |

## Stress and Sensitivity

| Family | Crash slip 0.30% | Crash slip 1.00% | Low-touch return | Low-touch MDD | Neighbor min return | Neighbor max MDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed threshold | 64.78% | 61.33% | 102.47% | 22.72% | 54.62% | 26.14% |
| ATR adaptive | 70.35% | 54.92% | 70.53% | 11.90% | 17.22% | 37.62% |
| Two-stage defense | 49.56% | 32.25% | 51.86% | 19.86% | 37.00% | 26.87% |

## Limitations

- The recommended rule had zero emergency exits in validation; the holdout confirms low strategy drag, not crash-defense effectiveness.
- Manual recovery delays are a modeling proxy; the live bot still requires an explicit operator unlock unless separately redesigned.
- Ranking uses completed five-minute OHLC closes and next-candle opens; it cannot reconstruct two observations ten seconds apart.
- The low-touch run is a sensitivity bound, not proof that an intrabar condition lasted long enough to trade.
- Historical results do not guarantee future performance, and live liquidity can exceed the tested slippage.
- This report does not change the AWS live bot or place an order.
