# Bitget BTCUSDT 1x Long/Short Backtest

## 결론

- 판정: **not recommended**
- 검증 구간 선택 전략: **regime_filtered**
- 주의: negative holdout return after base costs
- 본 연구는 모의 백테스트이며 즉시 실거래를 권장하지 않습니다.

## Data

- Market: `BTCUSDT`
- First candle: `2026-01-01T00:00:00+00:00`
- Last candle: `2026-06-30T23:55:00+00:00`
- Candles: `52128`; missing: `0`; funding: `246`
- Funding coverage warning: Bitget API records begin at `2026-04-10T00:00:00+00:00`; earlier test settlements were unavailable and treated as zero.

## Full

| Strategy | Return | MDD | Cycles | Fee | Slippage | Funding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 현금 보유 | 0.00% | 0.00% | 0 | 0.00 USDT | 0.00 USDT | 0.00 USDT |
| BTC 1배 보유 | -33.35% | 40.40% | 1 | 3.00 USDT | 1.00 USDT | -1.96 USDT |
| 롱 전용 | -63.51% | 65.20% | 493 | 1231.99 USDT | 410.66 USDT | -2.51 USDT |
| 숏 전용 | -47.00% | 49.01% | 607 | 1410.08 USDT | 470.03 USDT | -2.42 USDT |
| 롱·숏 양방향 | -71.75% | 73.96% | 823 | 1725.76 USDT | 575.25 USDT | -4.05 USDT |
| 장세 필터 양방향 | -45.02% | 47.43% | 485 | 1272.08 USDT | 424.03 USDT | 1.64 USDT |

## Development

| Strategy | Return | MDD | Cycles | Fee | Slippage | Funding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 현금 보유 | 0.00% | 0.00% | 0 | 0.00 USDT | 0.00 USDT | 0.00 USDT |
| BTC 1배 보유 | -12.91% | 38.57% | 1 | 3.37 USDT | 1.12 USDT | 6.51 USDT |
| 롱 전용 | -45.39% | 47.66% | 327 | 922.29 USDT | 307.43 USDT | 1.84 USDT |
| 숏 전용 | -38.68% | 39.00% | 395 | 1042.45 USDT | 347.48 USDT | -2.81 USDT |
| 롱·숏 양방향 | -58.13% | 59.53% | 537 | 1353.99 USDT | 451.33 USDT | -0.29 USDT |
| 장세 필터 양방향 | -37.13% | 38.63% | 302 | 909.85 USDT | 303.28 USDT | 1.91 USDT |

## Holdout

| Strategy | Return | MDD | Cycles | Fee | Slippage | Funding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 현금 보유 | 0.00% | 0.00% | 0 | 0.00 USDT | 0.00 USDT | 0.00 USDT |
| BTC 1배 보유 | -23.79% | 29.90% | 1 | 3.18 USDT | 1.06 USDT | -9.91 USDT |
| 롱 전용 | -33.30% | 35.70% | 166 | 566.10 USDT | 188.70 USDT | -8.14 USDT |
| 숏 전용 | -13.39% | 16.65% | 212 | 600.75 USDT | 200.25 USDT | 0.64 USDT |
| 롱·숏 양방향 | -32.53% | 36.64% | 286 | 887.93 USDT | 295.98 USDT | -9.17 USDT |
| 장세 필터 양방향 | -12.70% | 17.17% | 183 | 575.13 USDT | 191.71 USDT | -0.62 USDT |

## 장세별 해석

상승장, 하락장, 중립장은 과거 정보만 사용한 4시간 EMA50/EMA200으로 구분했습니다.

## 한계

- 완성된 5분봉 신호를 다음 봉 시가에 체결했습니다.
- 수수료, 슬리피지, 실제 과거 펀딩비를 반영했지만 호가 충격은 단순화했습니다.
- HUNT 실거래 코드와 AWS 서비스는 변경하지 않았습니다.
