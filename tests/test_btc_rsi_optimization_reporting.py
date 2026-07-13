from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.btc_rsi_optimization import RsiThresholds, optimize_btc_rsi
from huntbot.btc_rsi_optimization_reporting import render_optimization_html, render_optimization_markdown
from huntbot.models import Candle


def fixture_study():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(40):
        price = Decimal("100") + Decimal(i % 8)
        candles.append(Candle("BTCUSDT", 5, start + timedelta(minutes=5 * i), price, price, price, price, Decimal("1")))
    return optimize_btc_rsi(
        candles,
        [],
        start,
        start + timedelta(minutes=200),
        thresholds=(RsiThresholds(45, 40, 60, 65, None, None, None, None),),
        rsi_values={item.timestamp: 44.0 if i % 10 == 0 else 66.0 if i % 10 == 5 else 50.0 for i, item in enumerate(candles)},
        holdout_start=start + timedelta(minutes=125),
    )


def test_optimization_reports_are_korean_standalone_and_include_thresholds():
    metadata = {"market": "BTCUSDT", "candle_count": 40, "missing_intervals": 0}
    html = render_optimization_html(fixture_study(), metadata)
    markdown = render_optimization_markdown(fixture_study(), metadata)

    assert "<!doctype html>" in html.lower()
    assert "RSI 최적화" in html
    assert "롱 전용" in html
    assert "45/40" in html
    assert "<script src=" not in html and "https://cdn" not in html
    assert "실거래" in markdown
    assert "Holdout" in markdown
