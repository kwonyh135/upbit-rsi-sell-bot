import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from huntbot.crash_backtest import CrashBacktestResult, CrashStudyResult, StudyCandidate, is_balanced_eligible


FAMILY_LABELS = {
    "fixed": "Fixed threshold",
    "adaptive": "ATR adaptive",
    "staged": "Two-stage defense",
}


def render_crash_study_markdown(study: CrashStudyResult, metadata: dict) -> str:
    recommendation = study.recommendation
    lines = [
        "# KRW-HUNT Crash Protection Backtest",
        "",
        "## Data",
        "",
        f"- Market: `{metadata['market']}`",
        f"- First candle: `{metadata['first_candle']}`",
        f"- Last candle: `{metadata['last_candle']}`",
        f"- Candle count: `{metadata['candle_count']}`",
        f"- Missing five-minute intervals: `{metadata['missing_intervals']}`",
        "",
        "## Recommendation",
        "",
        f"- Meets 90% validation-return requirement: **{'yes' if study.recommendation_eligible else 'no'}**",
        f"- Protection: **{FAMILY_LABELS[recommendation.protection.family]}** (`{recommendation.protection.name}`)",
        f"- Recovery: **{recommendation.recovery.name}**",
        f"- Validation return: **{_pct(recommendation.validation.return_pct)}**",
        f"- Validation MDD: **{_pct(recommendation.validation.max_drawdown_pct)}**",
        f"- Full-period return: **{_pct(recommendation.full.return_pct)}**",
        f"- Full-period MDD: **{_pct(recommendation.full.max_drawdown_pct)}**",
        f"- Emergency exits: **{recommendation.full.emergency_exits}**",
        "",
        "## Baselines",
        "",
        "| Strategy | Return | MDD | Emergency exits |",
        "| --- | ---: | ---: | ---: |",
        _baseline_row("No protection baseline", study.baseline_full),
        _baseline_row("Previous 7%/10% permanent halt reference", study.current_reference),
        "",
        "## User-selected live rule (6% / 5% / 2 candles)",
        "",
        "This rule was selected by the user after the optimization study; it is not relabeled as the prior historical optimum.",
        "",
        "| Scenario | Return | MDD | Emergency exits | False exits |",
        "| --- | ---: | ---: | ---: | ---: |",
        _live_rule_row("Manual immediate-unlock proxy", study.live_rule_immediate),
        _live_rule_row("Permanent halt", study.live_rule_permanent),
        _live_rule_row("Manual immediate, crash slip 0.30%", study.live_rule_stress_030),
        _live_rule_row("Manual immediate, crash slip 1.00%", study.live_rule_stress_100),
        "",
        (
            "Compared with no protection, the immediate-unlock proxy changes return by "
            f"**{_signed_pp(study.live_rule_immediate.return_pct - study.baseline_full.return_pct)}** "
            "and MDD by "
            f"**{_signed_pp(study.live_rule_immediate.max_drawdown_pct - study.baseline_full.max_drawdown_pct)}**."
        ),
        "",
        "## Family Winners",
        "",
        "| Family | Recovery | Eligible | Validation Return | Validation MDD | Validation exits | Full Return | Full MDD | Emergency exits | False exits |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for candidate in study.family_winners:
        lines.append(_candidate_row(candidate, study.baseline_validation))
    lines.extend(
        [
            "",
            "## Stress and Sensitivity",
            "",
            "| Family | Crash slip 0.30% | Crash slip 1.00% | Low-touch return | Low-touch MDD | Neighbor min return | Neighbor max MDD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for candidate in study.family_winners:
        lines.append(
            f"| {FAMILY_LABELS[candidate.protection.family]} "
            f"| {_pct(candidate.stress_030.return_pct)} "
            f"| {_pct(candidate.stress_100.return_pct)} "
            f"| {_pct(candidate.low_touch.return_pct)} "
            f"| {_pct(candidate.low_touch.max_drawdown_pct)} "
            f"| {_pct(candidate.neighbor_min_return)} "
            f"| {_pct(candidate.neighbor_max_mdd)} |"
        )
    holdout_warning = []
    if recommendation.validation.emergency_exits == 0:
        holdout_warning = [
            "- The recommended rule had zero emergency exits in validation; the holdout confirms low strategy drag, not crash-defense effectiveness.",
        ]
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            *holdout_warning,
            "- Manual recovery delays are a modeling proxy; the live bot still requires an explicit operator unlock unless separately redesigned.",
            "- Ranking uses completed five-minute OHLC closes and next-candle opens; it cannot reconstruct two observations ten seconds apart.",
            "- The low-touch run is a sensitivity bound, not proof that an intrabar condition lasted long enough to trade.",
            "- Historical results do not guarantee future performance, and live liquidity can exceed the tested slippage.",
            "- This report does not change the AWS live bot or place an order.",
        ]
    )
    return "\n".join(lines) + "\n"


def study_to_json(study: CrashStudyResult, metadata: dict) -> str:
    payload = {"metadata": metadata, "study": asdict(study), "recommendation": asdict(study.recommendation)}
    return json.dumps(payload, indent=2, ensure_ascii=True, default=_json_default) + "\n"


def _pct(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}%"


def _signed_pp(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):+} pp"


def _baseline_row(label: str, result: CrashBacktestResult) -> str:
    return f"| {label} | {_pct(result.return_pct)} | {_pct(result.max_drawdown_pct)} | {result.emergency_exits} |"


def _live_rule_row(label: str, result: CrashBacktestResult) -> str:
    return (
        f"| {label} | {_pct(result.return_pct)} | {_pct(result.max_drawdown_pct)} "
        f"| {result.emergency_exits} | {result.false_exits} |"
    )


def _candidate_row(candidate: StudyCandidate, baseline: CrashBacktestResult) -> str:
    eligible = is_balanced_eligible(
        candidate.validation.return_pct,
        baseline.return_pct,
    )
    return (
        f"| {FAMILY_LABELS[candidate.protection.family]} "
        f"| {candidate.recovery.name} "
        f"| {'yes' if eligible else 'no'} "
        f"| {_pct(candidate.validation.return_pct)} "
        f"| {_pct(candidate.validation.max_drawdown_pct)} "
        f"| {candidate.validation.emergency_exits} "
        f"| {_pct(candidate.full.return_pct)} "
        f"| {_pct(candidate.full.max_drawdown_pct)} "
        f"| {candidate.full.emergency_exits} "
        f"| {candidate.full.false_exits} |"
    )


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value)!r}")
