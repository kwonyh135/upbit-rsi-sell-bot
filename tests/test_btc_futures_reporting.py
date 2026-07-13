from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.btc_futures_reporting import render_btc_html, render_btc_markdown
from huntbot.btc_futures_study import run_btc_futures_study
from huntbot.models import Candle


def fixture_study():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for i in range(40):
        price = Decimal("100") + Decimal(i % 10)
        candles.append(Candle("BTCUSDT", 5, start + timedelta(minutes=5 * i), price, price, price, price, Decimal("1")))
    return run_btc_futures_study(candles, [], start, start + timedelta(minutes=200), holdout_start=start + timedelta(minutes=125))


def metadata():
    return {"market": "BTCUSDT", "first_candle": "2026-01-01T00:00:00+00:00", "last_candle": "2026-06-30T23:55:00+00:00", "candle_count": 52560, "missing_intervals": 0, "funding_count": 540}


def test_html_is_standalone_korean_and_contains_required_sections():
    html = render_btc_html(fixture_study(), metadata())
    assert "<!doctype html>" in html.lower()
    assert "상승장" in html and "하락장" in html and "검증 구간" in html
    assert "수수료" in html and "펀딩비" in html and "최대 낙폭" in html
    assert "<svg" in html
    assert "https://cdn" not in html and "<script src=" not in html


def test_report_never_labels_result_as_ready_for_live_trading():
    html = render_btc_html(fixture_study(), metadata())
    markdown = render_btc_markdown(fixture_study(), metadata())
    assert "즉시 실거래 권장" not in html
    assert "실거래 코드를 변경하지" in html
    assert "Holdout" in markdown and "MDD" in markdown
