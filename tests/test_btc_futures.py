from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib

import pytest

from huntbot.models import Candle
from huntbot.bitget_public import FundingSettlement


START = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)


def _btc():
    return importlib.import_module("huntbot.btc_futures")


def candle_at(
    offset_minutes: int,
    close: str = "100",
    *,
    market: str = "BTCUSDT",
    unit: int = 5,
    volume: str = "1",
    base: datetime = START,
) -> Candle:
    price = Decimal(close)
    return Candle(
        market=market,
        unit=unit,
        timestamp=base + timedelta(minutes=offset_minutes),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(volume),
    )


def synthetic_trend_candles(four_hour_bar_closes: list[str]) -> list[Candle]:
    candles: list[Candle] = []
    base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    for bar_index, close in enumerate(four_hour_bar_closes):
        for offset in range(48):
            candles.append(candle_at((bar_index * 48 + offset) * 5, close=close, base=base))
    return candles


def test_validate_candles_deduplicates_identical_duplicates_and_counts_warmup_gaps():
    btc = _btc()
    candles = [
        candle_at(-15, close="98"),
        candle_at(-5, close="99"),
        candle_at(0, close="100"),
        candle_at(5, close="101"),
        candle_at(5, close="101"),
        candle_at(10, close="102"),
    ]

    validated, missing_intervals = btc.validate_candles(candles, START, END)

    assert [item.timestamp for item in validated] == [
        START - timedelta(minutes=15),
        START - timedelta(minutes=5),
        START,
        START + timedelta(minutes=5),
        START + timedelta(minutes=10),
    ]
    assert missing_intervals == 1


def test_validate_candles_normalizes_kst_timestamps_and_aligns_buckets_to_utc():
    btc = _btc()
    kst = timezone(timedelta(hours=9))
    base = datetime(2026, 1, 1, 8, 0, tzinfo=kst)
    candles = [
        candle_at(offset * 5, close="100" if offset < 60 else "200", base=base)
        for offset in range(144)
    ]

    validated, missing_intervals = btc.validate_candles(
        candles,
        base.astimezone(timezone.utc),
        base.astimezone(timezone.utc) + timedelta(hours=12),
    )
    regimes = btc.classify_regimes(candles)

    assert validated[0].timestamp.tzinfo == timezone.utc
    assert missing_intervals == 0
    assert regimes[candles[96].timestamp.astimezone(timezone.utc)] == btc.Regime.NEUTRAL
    assert regimes[candles[108].timestamp.astimezone(timezone.utc)] == btc.Regime.BULL


def test_validate_candles_rejects_conflicting_duplicate():
    btc = _btc()
    candles = [candle_at(0, close="100"), candle_at(0, close="101")]

    with pytest.raises(ValueError, match="conflicting duplicate"):
        btc.validate_candles(candles, START, START + timedelta(minutes=5))


def test_validate_candles_rejects_missing_required_interval():
    btc = _btc()
    candles = [
        candle_at(-5, close="99"),
        candle_at(0, close="100"),
        candle_at(10, close="102"),
    ]

    with pytest.raises(ValueError, match="missing 1 required five-minute interval"):
        btc.validate_candles(candles, START, END)


def test_validate_candles_deduplicates_volume_only_duplicate_rows():
    btc = _btc()
    candles = [
        candle_at(0, close="100", volume="1"),
        candle_at(0, close="100", volume="2"),
        candle_at(5, close="101", volume="3"),
    ]

    validated, missing_intervals = btc.validate_candles(candles, START, START + timedelta(minutes=10))

    assert [item.timestamp for item in validated] == [
        START,
        START + timedelta(minutes=5),
    ]
    assert missing_intervals == 0


def test_regime_is_not_visible_until_four_hour_bar_closes():
    btc = _btc()
    candles = synthetic_trend_candles((["100"] * 200) + ["200", "200"])

    regimes = btc.classify_regimes(candles)

    jump_bar_start = candles[200 * 48].timestamp
    post_close_boundary = candles[201 * 48].timestamp
    assert regimes[jump_bar_start - timedelta(minutes=5)] == btc.Regime.NEUTRAL
    assert regimes[jump_bar_start] == btc.Regime.NEUTRAL
    assert regimes[post_close_boundary] == btc.Regime.BULL


def test_desired_targets_are_symmetric_and_regime_filtered():
    btc = _btc()
    assert btc.desired_target(btc.StrategyKind.LONG_ONLY, Decimal("0"), 44, btc.Regime.BEAR) == Decimal("0.5")
    assert btc.desired_target(btc.StrategyKind.SHORT_ONLY, Decimal("0"), 61, btc.Regime.BULL) == Decimal("-0.5")
    assert btc.desired_target(btc.StrategyKind.REGIME_FILTERED, Decimal("0"), 44, btc.Regime.BEAR) == Decimal("0")
    assert btc.desired_target(btc.StrategyKind.REGIME_FILTERED, Decimal("0"), 61, btc.Regime.BEAR) == Decimal("-0.5")


def test_backtest_executes_signal_at_next_open_with_adverse_slippage():
    btc = _btc()
    candles = [candle_at(i * 5, close=str(100 + i)) for i in range(4)]
    candles[1] = Candle("BTCUSDT", 5, candles[1].timestamp, Decimal("102"), Decimal("103"), Decimal("101"), Decimal("102"), Decimal("1"))
    rsi_values = {candles[0].timestamp: 44.0, candles[1].timestamp: 50.0, candles[2].timestamp: 66.0}
    config = btc.FuturesConfig(kind=btc.StrategyKind.LONG_ONLY, slippage=Decimal("0.0002"))

    result = btc.run_futures_backtest(candles, [], {}, config, rsi_values=rsi_values)

    assert result.trades[0].timestamp == candles[1].timestamp
    assert result.trades[0].market_price == Decimal("102")
    assert result.trades[0].execution_price == Decimal("102.0204")
    assert result.trades[0].target_exposure == Decimal("0.5")


def test_positive_funding_is_paid_by_long_and_received_by_short():
    btc = _btc()
    candles = [candle_at(i * 5, close="100") for i in range(4)]
    funding = [FundingSettlement(candles[2].timestamp, Decimal("0.001"))]
    long_rsi = {candles[0].timestamp: 44.0}
    short_rsi = {candles[0].timestamp: 61.0}

    long = btc.run_futures_backtest(candles, funding, {}, btc.FuturesConfig(btc.StrategyKind.LONG_ONLY), rsi_values=long_rsi)
    short = btc.run_futures_backtest(candles, funding, {}, btc.FuturesConfig(btc.StrategyKind.SHORT_ONLY), rsi_values=short_rsi)

    assert long.funding_pnl < 0
    assert short.funding_pnl > 0


def test_each_fill_charges_taker_fee_and_exposure_stays_bounded():
    btc = _btc()
    candles = [candle_at(i * 5, close="100") for i in range(4)]
    result = btc.run_futures_backtest(
        candles,
        [],
        {},
        btc.FuturesConfig(btc.StrategyKind.LONG_ONLY, initial_equity=Decimal("3000"), fee_rate=Decimal("0.0006"), slippage=Decimal("0")),
        rsi_values={candles[0].timestamp: 44.0},
    )

    assert result.trades[0].fee == Decimal("0.9")
    assert all(Decimal("-1") <= point.exposure <= Decimal("1") for point in result.equity_curve)


def test_direct_reversal_closes_first_and_waits_for_later_signal():
    btc = _btc()
    assert btc._guard_reversal(Decimal("0.5"), Decimal("-0.5")) == Decimal("0")
    assert btc._guard_reversal(Decimal("0"), Decimal("-0.5")) == Decimal("-0.5")


def test_buy_and_hold_does_not_rebalance_on_every_candle():
    btc = _btc()
    candles = [candle_at(i * 5, close=str(100 + i)) for i in range(30)]
    result = btc.run_futures_backtest(candles, [], {}, btc.FuturesConfig(btc.StrategyKind.BUY_AND_HOLD))
    assert len(result.trades) == 2
    assert result.trades[0].target_exposure == Decimal("1")
    assert result.trades[-1].reason == "end_of_test"


def test_unchanged_rsi_target_does_not_create_micro_rebalances():
    btc = _btc()
    candles = [candle_at(i * 5, close=str(100 + i)) for i in range(8)]
    rsi_values = {item.timestamp: 44.0 for item in candles[:-1]}
    result = btc.run_futures_backtest(
        candles, [], {}, btc.FuturesConfig(btc.StrategyKind.LONG_ONLY), rsi_values=rsi_values
    )
    assert len(result.trades) == 2
