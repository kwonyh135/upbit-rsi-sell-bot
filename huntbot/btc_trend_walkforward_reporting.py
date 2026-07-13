from __future__ import annotations

from decimal import Decimal
from html import escape

from huntbot.btc_trend_walkforward import FixedLookbackSummary, WalkForwardFold, WalkForwardStudy


def _pct(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}%"


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def render_walkforward_markdown(study: WalkForwardStudy, metadata: dict) -> str:
    warning = []
    if not metadata.get("funding_coverage_complete", True):
        warning.append(
            f"- Funding coverage warning: Bitget funding records begin at `{metadata.get('funding_first')}`; earlier settlements were unavailable and treated as zero."
        )
    lines = [
        "# BTC Donchian Trend Walk-Forward Report",
        "",
        "## Judgment",
        "",
        f"- Conclusion: **{study.conclusion}**",
        f"- Method: `{study.train_months}` months train -> `{study.test_months}` months out-of-sample test, rolled forward by the test window.",
        f"- Lookback candidates: `{', '.join(str(item) for item in study.lookbacks)}`",
        f"- Selected walk-forward compounded return: **{_pct(study.selected_summary.compounded_return_pct)}**",
        f"- Selected walk-forward stress return: **{_pct(study.selected_summary.stress_compounded_return_pct)}**",
        f"- Selected worst fold: **{_pct(study.selected_summary.worst_fold_return_pct)}**",
        f"- Selected max fold MDD: **{_pct(study.selected_summary.max_drawdown_pct)}**",
        *[f"- Caution: {reason}" for reason in study.conclusion_reasons],
        *warning,
        "",
        "## Out-Of-Sample Folds",
        "",
        "|Fold|Train|Test|Selected|Train Stress|Test|Stress|MDD|Cycles|Win|Long|Short|",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        *[_fold_row(fold) for fold in study.folds],
        "",
        "## Fixed Lookback Comparison On The Same OOS Windows",
        "",
        "|Lookback|Compounded|Stress|Worst|Worst Stress|Max MDD|Cycles|Positive Folds|Long|Short|",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        *[_summary_row(item, len(study.folds)) for item in study.fixed_summaries],
        "",
        "## Interpretation",
        "",
        "Walk-forward testing is stricter than the previous full-period search because each fold chooses the lookback using only the prior training window, then applies it to the next unseen test window.",
        "If the selected values keep clustering around the same area and the out-of-sample stress return remains positive, the overfitting concern decreases. If selections jump around or the next-window result collapses, the previous full-period result was likely too curve-fit.",
        "",
        "This report is research-only. It does not change the Upbit HUNT bot, AWS service, or any live trading code.",
    ]
    return "\n".join(lines) + "\n"


def _fold_row(fold: WalkForwardFold) -> str:
    return (
        f"|{fold.index}|{fold.train_start.date()}~{fold.train_end.date()}|"
        f"{fold.test_start.date()}~{fold.test_end.date()}|{fold.selected_lookback}|"
        f"{_pct(fold.selected_train_stress_pct)}|{_pct(fold.test.return_pct)}|"
        f"{_pct(fold.test_stress.return_pct)}|{_pct(fold.test.max_drawdown_pct)}|"
        f"{len(fold.test.cycles)}|{_pct(fold.test.win_rate_pct)}|"
        f"{_money(fold.test.long_pnl)}|{_money(fold.test.short_pnl)}|"
    )


def _summary_row(item: FixedLookbackSummary, fold_count: int) -> str:
    return (
        f"|{item.lookback}|{_pct(item.compounded_return_pct)}|{_pct(item.stress_compounded_return_pct)}|"
        f"{_pct(item.worst_fold_return_pct)}|{_pct(item.worst_fold_stress_pct)}|"
        f"{_pct(item.max_drawdown_pct)}|{item.total_cycles}|{item.positive_folds}/{fold_count}|"
        f"{_money(item.long_pnl)}|{_money(item.short_pnl)}|"
    )


def render_walkforward_html(study: WalkForwardStudy, metadata: dict) -> str:
    fold_rows = "".join(_html_fold_row(fold) for fold in study.folds)
    summary_rows = "".join(_html_summary_row(item, len(study.folds)) for item in study.fixed_summaries)
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in study.conclusion_reasons) or "<li>No automatic rejection reason was triggered, but paper-trading validation is still required.</li>"
    funding = ""
    if not metadata.get("funding_coverage_complete", True):
        funding = f"<p><b>Funding coverage warning:</b> records begin at {escape(str(metadata.get('funding_first')))}; earlier settlements were treated as zero.</p>"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>BTC Trend Walk-Forward</title>
<style>
body{{font-family:Arial,'Malgun Gothic',sans-serif;margin:32px;background:#f6f7fb;color:#172033;line-height:1.5}}
.card{{background:white;border-radius:16px;padding:22px;margin:16px 0;box-shadow:0 8px 24px rgba(15,23,42,.08)}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.metric{{background:#eef2ff;border-radius:12px;padding:14px}}.metric b{{display:block;font-size:1.35rem}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3){{text-align:left}}th{{background:#111827;color:white}}
.warn{{background:#fff7ed;color:#7c2d12}}.good{{background:#ecfdf5;color:#065f46}}
</style></head><body>
<section class="card"><h1>BTC Donchian Trend Walk-Forward</h1><p>6개월 학습 후 다음 3개월 미지 구간에 적용하는 연구 전용 검증입니다.</p></section>
<section class="card warn"><strong>Judgment:</strong> {escape(study.conclusion)}<ul>{reasons}</ul>{funding}</section>
<section class="card"><h2>Summary</h2><div class="metrics">
<div class="metric">Selected OOS<b>{_pct(study.selected_summary.compounded_return_pct)}</b></div>
<div class="metric">Stress OOS<b>{_pct(study.selected_summary.stress_compounded_return_pct)}</b></div>
<div class="metric">Worst Fold<b>{_pct(study.selected_summary.worst_fold_return_pct)}</b></div>
<div class="metric">Max Fold MDD<b>{_pct(study.selected_summary.max_drawdown_pct)}</b></div>
</div></section>
<section class="card"><h2>Out-Of-Sample Folds</h2><table><thead><tr><th>Fold</th><th>Train</th><th>Test</th><th>Selected</th><th>Train Stress</th><th>Test</th><th>Stress</th><th>MDD</th><th>Cycles</th><th>Win</th><th>Long</th><th>Short</th></tr></thead><tbody>{fold_rows}</tbody></table></section>
<section class="card"><h2>Fixed Lookback Comparison</h2><table><thead><tr><th>Lookback</th><th>Compounded</th><th>Stress</th><th>Worst</th><th>Worst Stress</th><th>Max MDD</th><th>Cycles</th><th>Positive</th><th>Long</th><th>Short</th></tr></thead><tbody>{summary_rows}</tbody></table></section>
<section class="card good"><h2>How To Read This</h2><p>워크포워드는 전체 기간을 보고 고르는 방식보다 엄격합니다. 학습 구간에서 고른 lookback이 바로 다음 미지 구간에서도 살아남는지 확인하므로, 과최적화 여부를 더 잘 드러냅니다.</p><p>이 보고서는 실거래 코드나 AWS 서비스를 변경하지 않습니다.</p></section>
</body></html>"""


def _html_fold_row(fold: WalkForwardFold) -> str:
    values = (
        str(fold.index),
        f"{fold.train_start.date()}~{fold.train_end.date()}",
        f"{fold.test_start.date()}~{fold.test_end.date()}",
        str(fold.selected_lookback),
        _pct(fold.selected_train_stress_pct),
        _pct(fold.test.return_pct),
        _pct(fold.test_stress.return_pct),
        _pct(fold.test.max_drawdown_pct),
        str(len(fold.test.cycles)),
        _pct(fold.test.win_rate_pct),
        _money(fold.test.long_pnl),
        _money(fold.test.short_pnl),
    )
    return "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in values) + "</tr>"


def _html_summary_row(item: FixedLookbackSummary, fold_count: int) -> str:
    values = (
        str(item.lookback),
        _pct(item.compounded_return_pct),
        _pct(item.stress_compounded_return_pct),
        _pct(item.worst_fold_return_pct),
        _pct(item.worst_fold_stress_pct),
        _pct(item.max_drawdown_pct),
        str(item.total_cycles),
        f"{item.positive_folds}/{fold_count}",
        _money(item.long_pnl),
        _money(item.short_pnl),
    )
    return "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in values) + "</tr>"


__all__ = ["render_walkforward_html", "render_walkforward_markdown"]
