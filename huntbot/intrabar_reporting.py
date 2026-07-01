import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from huntbot.intrabar_backtest import TimingBacktestResult
from huntbot.intrabar_signals import TimingMode
from huntbot.intrabar_study import TimingStudyResult


FEE_RATE = Decimal("0.0005")


def render_timing_study_markdown(study: TimingStudyResult, metadata: dict) -> str:
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
        f"Recommendation: **{study.recommendation}**",
        "",
        f"Reason: {study.recommendation_reason}.",
    ]
    for segment, title in (
        ("full", "Full Period"),
        ("training", "Training"),
        ("holdout", "Holdout"),
    ):
        lines.extend(_matrix_section(title, study.runs[segment]))

    lines.extend(["", "## Cycle Concentration", ""])
    for mode, result in study.primary.items():
        lines.append(f"- {mode}: {_cycle_concentration(result)}")

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
            "- Signals fill at the next observed trade with fixed adverse slippage and a 0.05% fee.",
            "- Training and holdout restart from KRW 3,000,000 and do not continue full-period portfolio state.",
            "- Historical results do not guarantee future performance or available market liquidity.",
            "- This study does not change live commands, runtime state, or place orders.",
        ]
    )
    return "\n".join(lines) + "\n"


def timing_study_to_json(study: TimingStudyResult, metadata: dict) -> str:
    payload = {"metadata": metadata, "study": asdict(study)}
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        default=_json_default,
    ) + "\n"


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
    if not result.trades:
        return "no completed trade events"
    daily: dict[str, int] = {}
    for trade in result.trades:
        day = trade.timestamp.date().isoformat()
        daily[day] = daily.get(day, 0) + 1
    day, count = max(daily.items(), key=lambda item: (item[1], item[0]))
    share = Decimal(count) / Decimal(len(result.trades)) * Decimal("100")
    return f"busiest UTC day {day} held {count}/{len(result.trades)} events ({_pct(share)})"


def _event_difference(
    label: str,
    result: TimingBacktestResult,
    completed: TimingBacktestResult,
) -> str:
    events = {(trade.action, trade.signal_timestamp) for trade in result.trades}
    baseline = {(trade.action, trade.signal_timestamp) for trade in completed.trades}
    return (
        f"- {label} vs completed: {len(events - baseline)} unique events; "
        f"{len(baseline - events)} completed-mode events absent."
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
