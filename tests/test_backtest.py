from datetime import datetime, timezone
from decimal import Decimal

from huntbot.backtest import run_backtest, run_buyback_backtest
from huntbot.models import Candle


def candle(index: int, close: str) -> Candle:
    price = Decimal(close)
    return Candle(
        market="KRW-HUNT",
        unit=60,
        timestamp=datetime(2026, 1, 1, index % 24, tzinfo=timezone.utc),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1000"),
    )


def test_backtest_starts_with_3000000_krw_value():
    candles = [candle(i, str(100 + i)) for i in range(30)]
    result = run_backtest(candles, sell_rsi=70.0, reset_rsi=60.0, initial_krw=Decimal("3000000"))
    assert result.final_total_value > Decimal("0")
    assert result.unit == 60


def test_backtest_records_half_sell_when_rsi_overheats():
    closes = [100] * 15 + [110, 120, 130, 140, 150, 145, 140, 135, 130, 125, 140, 155, 170]
    candles = [candle(i, str(close)) for i, close in enumerate(closes)]
    result = run_backtest(candles, sell_rsi=70.0, reset_rsi=60.0, initial_krw=Decimal("3000000"))
    assert result.sell_count >= 1
    assert result.cash > Decimal("0")


def test_buyback_backtest_rebuys_cash_when_rsi_falls_to_buy_threshold():
    closes = [100] * 15 + [110, 120, 130, 140, 150, 145, 135, 125, 115, 105, 95, 90, 100]
    candles = [candle(i, str(close)) for i, close in enumerate(closes)]
    result = run_buyback_backtest(
        candles,
        sell_rsi=70.0,
        buy_rsi=45.0,
        initial_krw=Decimal("3000000"),
    )
    assert result.sell_count == 1
    assert result.buy_count == 1
    assert result.cash == Decimal("0")
