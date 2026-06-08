from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from huntbot.models import SplitBuybackBacktestResult, TradeEvent


def render_split_buyback_report(
    *,
    result: SplitBuybackBacktestResult,
    output_path: Path,
    data_through_kst: str,
    fee_rate: Decimal,
    slippage_rate: Decimal,
    recent_days: int = 90,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cutoff = result.events[-1].timestamp - timedelta(days=recent_days) if result.events else datetime.min.replace(tzinfo=timezone.utc)
    recent_events = [event for event in result.events if event.timestamp >= cutoff]
    output_path.write_text(
        _html_document(
            result=result,
            recent_events=recent_events,
            data_through_kst=data_through_kst,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            recent_days=recent_days,
        ),
        encoding="utf-8",
    )


def _html_document(
    *,
    result: SplitBuybackBacktestResult,
    recent_events: list[TradeEvent],
    data_through_kst: str,
    fee_rate: Decimal,
    slippage_rate: Decimal,
    recent_days: int,
) -> str:
    rows = "\n".join(_event_row(event) for event in recent_events)
    points = _sparkline_points(recent_events)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KRW-HUNT 5분봉 분할매매 이벤트</title>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; color: #1f2937; background: #f5f7fb; }}
    header {{ background: #fff; border-bottom: 1px solid #d8dee9; padding: 26px 30px; }}
    h1 {{ margin: 0 0 8px; font-size: 27px; letter-spacing: 0; }}
    p {{ color: #667085; line-height: 1.5; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .metric {{ background: #fff; border: 1px solid #d8dee9; border-radius: 8px; padding: 14px; min-height: 84px; }}
    .metric span {{ display: block; color: #667085; font-size: 13px; margin-bottom: 8px; }}
    .metric strong {{ font-size: 22px; }}
    .panel {{ background: #fff; border: 1px solid #d8dee9; border-radius: 8px; padding: 18px; margin-bottom: 18px; overflow-x: auto; }}
    svg {{ width: 100%; min-width: 760px; height: 300px; }}
    .line {{ fill: none; stroke: #2563eb; stroke-width: 2; }}
    .sell {{ fill: #b42318; }}
    .buy {{ fill: #15803d; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; min-width: 980px; }}
    th, td {{ border-bottom: 1px solid #d8dee9; padding: 10px 12px; text-align: left; font-size: 13px; }}
    th {{ color: #667085; background: #fbfcfe; }}
    code {{ background: #eef2f6; padding: 2px 5px; border-radius: 4px; }}
    @media (max-width: 760px) {{
      header {{ padding: 20px 16px; }}
      main {{ padding: 16px; }}
      .metrics {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>KRW-HUNT 5분봉 2단계 분할매매 이벤트</h1>
    <p>전체 백테스트 요약과 최근 {recent_days}일 매수/매도 이벤트입니다. 데이터 기준: {html.escape(data_through_kst)}.</p>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><span>최적 RSI</span><strong>매도 {result.sell_rsi_1:.0f}/{result.sell_rsi_2:.0f}, 매수 {result.buy_rsi_1:.0f}/{result.buy_rsi_2:.0f}</strong></div>
      <div class="metric"><span>전체 수익률</span><strong>{result.final_return_pct:.2f}%</strong></div>
      <div class="metric"><span>최종 평가금액</span><strong>{_krw(result.final_total_value)}</strong></div>
      <div class="metric"><span>비용 가정</span><strong>수수료 {fee_rate * 100:.2f}% / 슬리피지 {slippage_rate * 100:.2f}%</strong></div>
    </section>
    <section class="panel">
      <h2>최근 이벤트 가격 흐름</h2>
      <svg viewBox="0 0 1000 300" role="img" aria-label="recent trade event prices">
        <polyline class="line" points="{points}" />
        {_event_circles(recent_events)}
      </svg>
      <p><span style="color:#b42318">●</span> 매도, <span style="color:#15803d">●</span> 매수. 이벤트 사이 캔들 가격 전체가 아니라 실제 거래 이벤트 가격을 연결한 요약 흐름입니다.</p>
    </section>
    <section class="panel">
      <h2>최근 {recent_days}일 이벤트</h2>
      <table>
        <thead>
          <tr>
            <th>시간 UTC</th><th>액션</th><th>RSI</th><th>종가</th><th>체결가정가</th><th>평단가</th><th>실현손익</th><th>수량</th><th>현금</th><th>HUNT</th><th>평가금액</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Dry-run 시작</h2>
      <p><code>python -m huntbot watch-buyback-5m --dry-run</code>으로 실제 주문 없이 현재 RSI, 상태, 매수/매도 예정 액션을 확인합니다.</p>
    </section>
  </main>
</body>
</html>
"""


def _event_row(event: TradeEvent) -> str:
    action = html.escape(event.action)
    return (
        "<tr>"
        f"<td>{event.timestamp.isoformat()}</td>"
        f"<td>{action}</td>"
        f"<td>{event.rsi_value:.2f}</td>"
        f"<td>{_krw(event.close_price)}</td>"
        f"<td>{_krw(event.effective_price)}</td>"
        f"<td>{_krw(event.average_price)}</td>"
        f"<td>{_krw(event.realized_profit)}</td>"
        f"<td>{event.quantity:.8f}</td>"
        f"<td>{_krw(event.cash)}</td>"
        f"<td>{event.remaining_quantity:.8f}</td>"
        f"<td>{_krw(event.total_value)}</td>"
        "</tr>"
    )


def _sparkline_points(events: list[TradeEvent]) -> str:
    if not events:
        return ""
    prices = [event.close_price for event in events]
    low = min(prices)
    high = max(prices)
    span = high - low or Decimal("1")
    if len(events) == 1:
        return "500,150"
    points = []
    for index, event in enumerate(events):
        x = Decimal(index) / Decimal(len(events) - 1) * Decimal("940") + Decimal("30")
        y = Decimal("260") - ((event.close_price - low) / span * Decimal("220"))
        points.append(f"{float(x):.2f},{float(y):.2f}")
    return " ".join(points)


def _event_circles(events: list[TradeEvent]) -> str:
    if not events:
        return ""
    prices = [event.close_price for event in events]
    low = min(prices)
    high = max(prices)
    span = high - low or Decimal("1")
    circles = []
    for index, event in enumerate(events):
        x = Decimal(index) / Decimal(max(len(events) - 1, 1)) * Decimal("940") + Decimal("30")
        y = Decimal("260") - ((event.close_price - low) / span * Decimal("220"))
        klass = "sell" if event.action.startswith("sell") else "buy"
        circles.append(f'<circle class="{klass}" cx="{float(x):.2f}" cy="{float(y):.2f}" r="5"><title>{html.escape(event.action)} RSI {event.rsi_value:.2f}</title></circle>')
    return "\n        ".join(circles)


def _krw(value: Decimal) -> str:
    return f"{value.quantize(Decimal('1')):,}원"
