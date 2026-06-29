# KRW-HUNT Crash Protection Backtest

## Data

- Market: `KRW-HUNT`
- First candle: `2025-12-28T08:10:00+00:00`
- Last candle: `2026-06-29T08:00:00+00:00`
- Candle count: `26121`
- Missing five-minute intervals: `26582`

## Recommendation

- Meets 90% validation-return requirement: **yes**
- Protection: **Fixed threshold** (`fixed-w1-d6-l12-c2`)
- Recovery: **manual-6h**
- Validation return: **20.62%**
- Validation MDD: **21.92%**
- Full-period return: **73.51%**
- Full-period MDD: **21.92%**
- Emergency exits: **3**

## Baselines

| Strategy | Return | MDD | Emergency exits |
| --- | ---: | ---: | ---: |
| No protection baseline | 63.31% | 26.98% | 0 |
| Previous 7%/10% permanent halt reference | 3.34% | 14.46% | 1 |

## User-selected live rule (6% / 5% / 2 candles)

This rule was selected by the user after the optimization study; it is not relabeled as the prior historical optimum.

| Scenario | Return | MDD | Emergency exits | False exits |
| --- | ---: | ---: | ---: | ---: |
| Manual immediate-unlock proxy | 52.81% | 28.22% | 23 | 10 |
| Permanent halt | 9.51% | 5.95% | 1 | 0 |
| Manual immediate, crash slip 0.30% | 44.43% | 30.87% | 23 | 10 |
| Manual immediate, crash slip 1.00% | 23.26% | 37.80% | 23 | 12 |

Compared with no protection, the immediate-unlock proxy changes return by **-10.50 pp** and MDD by **+1.24 pp**.

## Family Winners

| Family | Recovery | Eligible | Validation Return | Validation MDD | Validation exits | Full Return | Full MDD | Emergency exits | False exits |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed threshold | manual-6h | yes | 20.62% | 21.92% | 0 | 73.51% | 21.92% | 3 | 1 |
| ATR adaptive | auto-6h | no | 7.27% | 20.70% | 8 | 65.13% | 22.04% | 23 | 8 |
| Two-stage defense | auto-3h | no | 0.79% | 22.72% | 8 | 59.51% | 22.72% | 23 | 8 |

## Stress and Sensitivity

| Family | Crash slip 0.30% | Crash slip 1.00% | Low-touch return | Low-touch MDD | Neighbor min return | Neighbor max MDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed threshold | 72.21% | 68.61% | 111.61% | 22.72% | 61.60% | 26.14% |
| ATR adaptive | 58.66% | 41.79% | 43.41% | 27.56% | 37.79% | 27.94% |
| Two-stage defense | 52.49% | 34.36% | 55.03% | 19.86% | 41.38% | 26.87% |

## Limitations

- The recommended rule had zero emergency exits in validation; the holdout confirms low strategy drag, not crash-defense effectiveness.
- Manual recovery delays are a modeling proxy; the live bot still requires an explicit operator unlock unless separately redesigned.
- Ranking uses completed five-minute OHLC closes and next-candle opens; it cannot reconstruct two observations ten seconds apart.
- The low-touch run is a sensitivity bound, not proof that an intrabar condition lasted long enough to trade.
- Historical results do not guarantee future performance, and live liquidity can exceed the tested slippage.
- This report does not change the AWS live bot or place an order.
