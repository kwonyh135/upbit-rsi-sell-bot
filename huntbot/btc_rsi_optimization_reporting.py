from __future__ import annotations

import html
from decimal import Decimal

from huntbot.btc_futures import StrategyKind
from huntbot.btc_rsi_optimization import BtcRsiOptimizationStudy, OptimizationCandidate, RsiThresholds


KIND_LABELS = {
    StrategyKind.LONG_ONLY: "롱 전용",
    StrategyKind.BIDIRECTIONAL: "롱·숏 양방향",
    StrategyKind.REGIME_FILTERED: "장세 필터 롱·숏",
}


def _fmt_pct(value: Decimal) -> str:
    return f"{value:.2f}%"


def _threshold_label(thresholds: RsiThresholds) -> str:
    long = f"롱 {thresholds.long_entry_1}/{thresholds.long_entry_2} → {thresholds.long_exit_1}/{thresholds.long_exit_2}"
    if thresholds.short_entry_1 is None:
        return long
    return f"{long}, 숏 {thresholds.short_entry_1}/{thresholds.short_entry_2} → {thresholds.short_exit_1}/{thresholds.short_exit_2}"


def _top_candidates(study: BtcRsiOptimizationStudy, limit: int = 20) -> list[OptimizationCandidate]:
    return sorted(
        study.candidates,
        key=lambda item: (
            item.holdout.result.return_pct,
            -item.holdout.result.max_drawdown_pct,
            item.stress_holdout.result.return_pct,
            item.development.result.return_pct,
        ),
        reverse=True,
    )[:limit]


def render_optimization_markdown(study: BtcRsiOptimizationStudy, metadata: dict) -> str:
    selected = study.selected
    rows = [
        "|순위|전략|RSI 기준|개발 수익|Holdout 수익|Holdout MDD|Stress 수익|거래 사이클|",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for index, candidate in enumerate(_top_candidates(study, 15), start=1):
        rows.append(
            f"|{index}|{KIND_LABELS.get(candidate.kind, candidate.kind.value)}|{_threshold_label(candidate.thresholds)}|"
            f"{_fmt_pct(candidate.development.result.return_pct)}|{_fmt_pct(candidate.holdout.result.return_pct)}|"
            f"{_fmt_pct(candidate.holdout.result.max_drawdown_pct)}|{_fmt_pct(candidate.stress_holdout.result.return_pct)}|"
            f"{len(candidate.holdout.result.cycles)}|"
        )
    reasons = ", ".join(study.conclusion_reasons) if study.conclusion_reasons else "검증 조건 통과"
    return "\n".join(
        [
            "# Bitget BTCUSDT RSI 최적화 보고서",
            "",
            f"- 기간: `{study.start.isoformat()}` ~ `{study.end.isoformat()}`",
            f"- Holdout 시작: `{study.holdout_start.isoformat()}`",
            f"- 캔들 수: `{metadata.get('candle_count')}`",
            f"- 결론: `{study.conclusion}` ({reasons})",
            f"- 선택 후보: `{KIND_LABELS.get(selected.kind, selected.kind.value)}` / `{_threshold_label(selected.thresholds)}`",
            "",
            "## 해석",
            "",
            "이 보고서는 RSI 기준을 바꿔 수익이 나는 조합이 있는지 찾기 위한 연구용 결과입니다. 실거래 코드는 변경하지 않았고, 선택 조합도 최소한 별도 모의운영이 필요합니다.",
            "",
            "## 상위 후보",
            "",
            *rows,
            "",
        ]
    )


def render_optimization_html(study: BtcRsiOptimizationStudy, metadata: dict) -> str:
    selected = study.selected
    rows = []
    for index, candidate in enumerate(_top_candidates(study), start=1):
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(KIND_LABELS.get(candidate.kind, candidate.kind.value))}</td>"
            f"<td>{html.escape(_threshold_label(candidate.thresholds))}</td>"
            f"<td>{_fmt_pct(candidate.development.result.return_pct)}</td>"
            f"<td>{_fmt_pct(candidate.holdout.result.return_pct)}</td>"
            f"<td>{_fmt_pct(candidate.holdout.result.max_drawdown_pct)}</td>"
            f"<td>{_fmt_pct(candidate.stress_holdout.result.return_pct)}</td>"
            f"<td>{len(candidate.holdout.result.cycles)}</td>"
            "</tr>"
        )
    reasons = ", ".join(study.conclusion_reasons) if study.conclusion_reasons else "검증 조건 통과"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Bitget BTCUSDT RSI 최적화</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; background: #f7f8fb; }}
    .card {{ background: white; border-radius: 16px; padding: 24px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08); margin-bottom: 18px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric {{ background: #eef2ff; border-radius: 12px; padding: 14px; }}
    .metric span {{ display: block; color: #596176; font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 10px; text-align: right; }}
    th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3) {{ text-align: left; }}
    th {{ background: #111827; color: white; }}
    .warn {{ color: #92400e; background: #fffbeb; border-radius: 12px; padding: 14px; }}
  </style>
</head>
<body>
  <section class="card">
    <h1>Bitget BTCUSDT RSI 최적화</h1>
    <p>RSI 기준 변경으로 수익 조합이 있는지 확인한 연구용 백테스트입니다. 실거래 코드는 변경하지 않았습니다.</p>
    <div class="metrics">
      <div class="metric"><span>선택 전략</span><strong>{html.escape(KIND_LABELS.get(selected.kind, selected.kind.value))}</strong></div>
      <div class="metric"><span>RSI 기준</span><strong>{html.escape(_threshold_label(selected.thresholds))}</strong></div>
      <div class="metric"><span>Holdout 수익</span><strong>{_fmt_pct(selected.holdout.result.return_pct)}</strong></div>
      <div class="metric"><span>Holdout MDD</span><strong>{_fmt_pct(selected.holdout.result.max_drawdown_pct)}</strong></div>
      <div class="metric"><span>Stress 수익</span><strong>{_fmt_pct(selected.stress_holdout.result.return_pct)}</strong></div>
      <div class="metric"><span>결론</span><strong>{html.escape(study.conclusion)}</strong></div>
    </div>
  </section>
  <section class="card warn">
    <strong>판단:</strong> {html.escape(reasons)}. 과최적화 가능성이 있으므로 실거래 전 별도 모의운영이 필요합니다.
  </section>
  <section class="card">
    <h2>상위 후보</h2>
    <table>
      <thead><tr><th>순위</th><th>전략</th><th>RSI 기준</th><th>개발 수익</th><th>Holdout 수익</th><th>Holdout MDD</th><th>Stress 수익</th><th>사이클</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>
</body>
</html>
"""


__all__ = ["render_optimization_html", "render_optimization_markdown"]
