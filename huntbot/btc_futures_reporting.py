from __future__ import annotations

from html import escape
from decimal import Decimal

from huntbot.btc_futures import FuturesResult, StrategyKind
from huntbot.btc_futures_study import BtcFuturesStudy, StudyRun


LABELS = {
    StrategyKind.CASH: "현금 보유",
    StrategyKind.BUY_AND_HOLD: "BTC 1배 보유",
    StrategyKind.LONG_ONLY: "롱 전용",
    StrategyKind.SHORT_ONLY: "숏 전용",
    StrategyKind.BIDIRECTIONAL: "롱·숏 양방향",
    StrategyKind.REGIME_FILTERED: "장세 필터 양방향",
}


def _pct(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}%"


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))} USDT"


def _base_runs(runs: tuple[StudyRun, ...]) -> list[StudyRun]:
    return [run for run in runs if run.result.config.slippage == Decimal("0.0002")]


def _md_rows(runs: tuple[StudyRun, ...]) -> list[str]:
    rows = []
    for run in _base_runs(runs):
        result = run.result
        rows.append(
            f"| {LABELS[result.config.kind]} | {_pct(result.return_pct)} | {_pct(result.max_drawdown_pct)} "
            f"| {len(result.cycles)} | {_money(result.fee_cost)} | {_money(result.slippage_cost)} | {_money(result.funding_pnl)} |"
        )
    return rows


def render_btc_markdown(study: BtcFuturesStudy, metadata: dict) -> str:
    funding_warning = [] if metadata.get("funding_coverage_complete", True) else [
        f"- Funding coverage warning: Bitget API records begin at `{metadata.get('funding_first')}`; earlier test settlements were unavailable and treated as zero."
    ]
    lines = [
        "# Bitget BTCUSDT 1x Long/Short Backtest",
        "", "## 결론", "",
        f"- 판정: **{study.conclusion}**",
        f"- 검증 구간 선택 전략: **{study.selected_strategy}**",
        *[f"- 주의: {reason}" for reason in study.conclusion_reasons],
        "- 본 연구는 모의 백테스트이며 즉시 실거래를 권장하지 않습니다.",
        "", "## Data", "",
        f"- Market: `{metadata['market']}`",
        f"- First candle: `{metadata['first_candle']}`",
        f"- Last candle: `{metadata['last_candle']}`",
        f"- Candles: `{metadata['candle_count']}`; missing: `{metadata['missing_intervals']}`; funding: `{metadata['funding_count']}`",
        *funding_warning,
    ]
    for title, runs in (("Full", study.full_runs), ("Development", study.development_runs), ("Holdout", study.holdout_runs)):
        lines.extend([
            "", f"## {title}", "",
            "| Strategy | Return | MDD | Cycles | Fee | Slippage | Funding |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *_md_rows(runs),
        ])
    lines.extend([
        "", "## 장세별 해석", "",
        "상승장, 하락장, 중립장은 과거 정보만 사용한 4시간 EMA50/EMA200으로 구분했습니다.",
        "", "## 한계", "",
        "- 완성된 5분봉 신호를 다음 봉 시가에 체결했습니다.",
        "- 수수료, 슬리피지, 실제 과거 펀딩비를 반영했지만 호가 충격은 단순화했습니다.",
        "- HUNT 실거래 코드와 AWS 서비스는 변경하지 않았습니다.",
    ])
    return "\n".join(lines) + "\n"


def _table(runs: tuple[StudyRun, ...]) -> str:
    rows = []
    for run in _base_runs(runs):
        r = run.result
        rows.append(
            "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in (
                LABELS[r.config.kind], _pct(r.return_pct), _pct(r.max_drawdown_pct), str(len(r.cycles)),
                _money(r.fee_cost), _money(r.slippage_cost), _money(r.funding_pnl), _pct(r.time_in_market_pct),
            )) + "</tr>"
        )
    return "<table><thead><tr><th>전략</th><th>수익률</th><th>최대 낙폭</th><th>사이클</th><th>수수료</th><th>슬리피지</th><th>펀딩비</th><th>시장 참여</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _selected_result(study: BtcFuturesStudy) -> FuturesResult:
    return next(
        run.result for run in study.full_runs
        if run.result.config.kind.value == study.selected_strategy and run.result.config.slippage == Decimal("0.0002")
    )


def _svg(result: FuturesResult, drawdown: bool = False) -> str:
    values = [point.equity for point in result.equity_curve]
    if not values:
        return "<svg viewBox='0 0 1000 260'></svg>"
    if drawdown:
        peak = Decimal("0")
        series = []
        for value in values:
            peak = max(peak, value)
            series.append((peak - value) / peak * Decimal("100") if peak else Decimal("0"))
        values = series
    low, high = min(values), max(values)
    span = high - low or Decimal("1")
    count = max(1, len(values) - 1)
    points = " ".join(
        f"{float(Decimal(i) / Decimal(count) * Decimal('980') + Decimal('10')):.2f},{float(Decimal('240') - (value - low) / span * Decimal('220')):.2f}"
        for i, value in enumerate(values)
    )
    return f"<svg viewBox='0 0 1000 260' role='img'><polyline points='{points}' fill='none' stroke='#48d597' stroke-width='2'/></svg>"


def render_btc_html(study: BtcFuturesStudy, metadata: dict) -> str:
    selected = _selected_result(study)
    reason_html = "".join(f"<li>{escape(reason)}</li>" for reason in study.conclusion_reasons) or "<li>선언된 검증 기준을 통과했습니다.</li>"
    funding_warning = "" if metadata.get("funding_coverage_complete", True) else (
        f"<p><b>펀딩 자료 제한:</b> 비트겟 공개 API가 {escape(str(metadata.get('funding_first')))} 이후 기록만 제공했습니다. "
        "그 이전 펀딩은 0으로 처리했으므로 비용 비교에는 불확실성이 있습니다.</p>"
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bitget BTC 롱·숏 백테스트</title><style>
:root{{--bg:#08131d;--card:#112331;--text:#edf6f2;--muted:#9fb5ae;--accent:#48d597}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Arial,'Malgun Gothic',sans-serif;line-height:1.55}}main{{max-width:1180px;margin:auto;padding:28px}}section{{background:var(--card);padding:22px;margin:18px 0;border-radius:14px}}h1,h2{{margin-top:0}}.badge{{display:inline-block;background:var(--accent);color:#062018;padding:7px 12px;border-radius:999px;font-weight:700}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}.metric{{background:#0b1b27;padding:14px;border-radius:10px}}.metric b{{display:block;font-size:1.3rem}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:840px}}th,td{{padding:9px;border-bottom:1px solid #29404d;text-align:right}}th:first-child,td:first-child{{text-align:left}}svg{{width:100%;height:260px;background:#0b1b27;border-radius:10px}}small,.muted{{color:var(--muted)}}
</style></head><body><main>
<h1>BTCUSDT 1배 롱·숏 백테스트</h1><p class="muted">비트겟 USDT-M 무기한 선물 · 최신 6개월 · 완성 5분봉</p>
<section><span class="badge">{escape(study.conclusion)}</span><h2>요약 결론</h2><p>검증 구간 선택 전략: <b>{escape(study.selected_strategy)}</b></p><ul>{reason_html}</ul><p><b>즉시 실거래 판단이 아닙니다.</b> 통과하더라도 추가 모의투자 단계만 권장합니다.</p></section>
<section><h2>데이터 품질</h2><div class="grid"><div class="metric">시장<b>{escape(str(metadata['market']))}</b></div><div class="metric">5분봉 수<b>{metadata['candle_count']}</b></div><div class="metric">누락 구간<b>{metadata['missing_intervals']}</b></div><div class="metric">펀딩 기록<b>{metadata['funding_count']}</b></div></div><p><small>UTC {escape(str(metadata['first_candle']))} ~ {escape(str(metadata['last_candle']))}; 보고서 날짜는 한국시간으로도 해석할 수 있습니다.</small></p>{funding_warning}</section>
<section><h2>전체 기간</h2><div class="table-wrap">{_table(study.full_runs)}</div></section>
<section><h2>개발 구간</h2><div class="table-wrap">{_table(study.development_runs)}</div></section>
<section><h2>검증 구간 (Holdout)</h2><div class="table-wrap">{_table(study.holdout_runs)}</div></section>
<section><h2>선택 전략 자산 곡선</h2>{_svg(selected)}<h2>최대 낙폭 흐름</h2>{_svg(selected, True)}</section>
<section><h2>상승장·하락장·중립장</h2><p>4시간 EMA50과 EMA200을 과거 정보만으로 계산했습니다. 상승장에서는 롱, 하락장에서는 숏을 허용한 필터 전략과 필터 없는 양방향 전략을 함께 비교했습니다.</p></section>
<section><h2>비용과 한계</h2><ul><li>시장가 수수료 편도 0.06%, 기본 슬리피지 0.02%, 스트레스 0.05%·0.10%</li><li>실제 과거 펀딩비 반영</li><li>완성 5분봉 신호를 다음 봉 시가에 체결</li><li>과거 성과는 미래 수익을 보장하지 않음</li><li>HUNT 실거래 코드와 AWS 서비스 및 실거래 코드를 변경하지 않았습니다.</li></ul></section>
</main></body></html>"""


__all__ = ["render_btc_html", "render_btc_markdown"]
