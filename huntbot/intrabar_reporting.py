import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from huntbot.intrabar_backtest import TimingBacktestResult
from huntbot.intrabar_signals import TimingMode
from huntbot.intrabar_study import TimingStudyResult


FEE_RATE = Decimal("0.0005")


def render_timing_study_markdown(study: TimingStudyResult, metadata: dict) -> str:
    recommendation, reason = _reported_recommendation(study, metadata)
    lines = [
        "# KRW-HUNT Intrabar RSI Timing Study",
        "",
        "## Coverage",
        "",
        f"- Market: `{metadata['market']}`",
        f"- First observed second: `{metadata['first_second']}`",
        f"- Last observed second: `{metadata['last_second']}`",
        f"- Observed trade seconds: `{metadata['second_count']}`",
        f"- Coverage days: `{metadata['coverage_days']}`",
        f"- Missing trade seconds: `{metadata['missing_trade_seconds']}`",
        f"- Chronological split: `{study.split_at.isoformat()}`",
        "",
        "## Recommendation",
        "",
        f"Recommendation: **{recommendation}**",
        "",
        f"Reason: {reason}.",
    ]
    for segment, title in (
        ("full", "Full Period"),
        ("training", "Training"),
        ("holdout", "Holdout"),
    ):
        lines.extend(_matrix_section(title, study.runs[segment]))

    lines.extend(["", "## Cycle Concentration", ""])
    for mode, result in study.primary.items():
        lines.append(
            f"- {mode}: Completed cycles: `{completed_cycle_count(result)}`; "
            f"{_cycle_concentration(result)}"
        )

    lines.extend(["", "## Event-Level Differences", ""])
    completed = study.primary[TimingMode.COMPLETED.value]
    for mode in (TimingMode.IMMEDIATE, TimingMode.HOLD_30S):
        lines.append(_event_difference(mode.value, study.primary[mode.value], completed))

    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Missing trade seconds are periods without observed trades, not reconstructed prices.",
            "- Completed-candle and emergency signals fill on the first boundary-or-later trade.",
            "- Intrabar signals fill on the next strictly later observed trade with fixed adverse slippage and a 0.05% fee.",
            "- Training and holdout restart from KRW 3,000,000 and do not continue full-period portfolio state.",
            "- Historical results do not guarantee future performance or available market liquidity.",
            "- This study does not change live commands, runtime state, or place orders.",
        ]
    )
    return "\n".join(lines) + "\n"


def timing_study_to_json(study: TimingStudyResult, metadata: dict) -> str:
    recommendation, reason = _reported_recommendation(study, metadata)
    serialized_study = asdict(study)
    serialized_study["recommendation"] = recommendation
    serialized_study["recommendation_reason"] = reason
    serialized_study["completed_cycles"] = {
        mode: completed_cycle_count(result)
        for mode, result in study.primary.items()
    }
    payload = {"metadata": metadata, "study": serialized_study}
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        default=_json_default,
    ) + "\n"


def completed_cycle_count(result: TimingBacktestResult) -> int:
    return len(result.cycles)


def _reported_recommendation(study: TimingStudyResult, metadata: dict) -> tuple[str, str]:
    if Decimal(str(metadata["coverage_days"])) < Decimal("60"):
        return "inconclusive", "coverage is under 60 days"
    cycle_counts = {
        mode: completed_cycle_count(result)
        for mode, result in study.primary.items()
    }
    if any(count < 2 for count in cycle_counts.values()):
        return (
            "inconclusive",
            "at least one primary full-period timing mode has fewer than two completed buy/sell cycles",
        )
    selected = study.primary.get(study.recommendation)
    if (
        study.recommendation != TimingMode.COMPLETED.value
        and selected is not None
        and _positive_cycle_share(selected) > Decimal("50")
    ):
        return "inconclusive", "one cycle contributed more than 50% of positive cycle P&L"
    return study.recommendation, study.recommendation_reason


def _matrix_section(
    title: str,
    runs: dict[str, TimingBacktestResult],
) -> list[str]:
    lines = [
        "",
        f"## {title} (18 runs)",
        "",
        "| Protection | Mode | Fee | Slippage | Return | MDD | Trades | False signals | Emergency exits | Fee cost | Slippage cost |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in sorted(runs):
        protection, slippage, mode = key.split(":")
        result = runs[key]
        fee_cost, slippage_cost = _costs(result)
        lines.append(
            f"| {protection} | {mode} | {_rate(FEE_RATE)} | {_rate(Decimal(slippage))} "
            f"| {_pct(result.return_pct)} | {_pct(result.max_drawdown_pct)} "
            f"| {len(result.trades)} | {result.false_intrabar_signals} | {result.emergency_exits} "
            f"| {_krw(fee_cost)} | {_krw(slippage_cost)} |"
        )
    return lines


def _costs(result: TimingBacktestResult) -> tuple[Decimal, Decimal]:
    fee_cost = Decimal("0")
    slippage_cost = Decimal("0")
    for trade in result.trades:
        fee_cost += trade.execution_price * trade.quantity * FEE_RATE
        slippage_cost += abs(trade.execution_price - trade.market_price) * trade.quantity
    return fee_cost, slippage_cost


def _cycle_concentration(result: TimingBacktestResult) -> str:
    if not result.cycles:
        return "no completed cycles"
    best = max(result.cycles, key=lambda cycle: cycle.pnl)
    worst = min(result.cycles, key=lambda cycle: cycle.pnl)
    return (
        f"best cycle P&L {_krw(best.pnl)} ({_pct(_positive_cycle_share(result))} of positive P&L); "
        f"worst cycle P&L {_krw(worst.pnl)}"
    )


def _positive_cycle_share(result: TimingBacktestResult) -> Decimal:
    positive = [cycle.pnl for cycle in result.cycles if cycle.pnl > 0]
    if not positive:
        return Decimal("0")
    return max(positive) / sum(positive, Decimal("0")) * Decimal("100")


def _event_difference(
    label: str,
    result: TimingBacktestResult,
    completed: TimingBacktestResult,
) -> str:
    events = {
        (trade.signal_candle_start, trade.action): trade
        for trade in result.trades
    }
    baseline = {
        (trade.signal_candle_start, trade.action): trade
        for trade in completed.trades
    }
    matched = events.keys() & baseline.keys()
    leads = [
        Decimal(str((baseline[key].signal_timestamp - events[key].signal_timestamp).total_seconds()))
        for key in matched
    ]
    mean_lead = sum(leads, Decimal("0")) / Decimal(len(leads)) if leads else Decimal("0")
    return (
        f"- {label} vs completed: {len(matched)} matched candle/action events; "
        f"mean signal lead {mean_lead:.2f}s; {len(events.keys() - baseline.keys())} mode-only; "
        f"{len(baseline.keys() - events.keys())} completed-only."
    )


def _rate(value: Decimal) -> str:
    return f"{value * Decimal('100'):.2f}%"


def _pct(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}%"


def _krw(value: Decimal) -> str:
    return f"{value.quantize(Decimal('1'))} KRW"


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value)!r}")
