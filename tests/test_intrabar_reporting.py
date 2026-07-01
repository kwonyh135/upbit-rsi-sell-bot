from datetime import datetime, timezone
from decimal import Decimal

from huntbot.intrabar_backtest import TimingBacktestResult, TimingTrade
from huntbot.intrabar_reporting import render_timing_study_markdown, timing_study_to_json
from huntbot.intrabar_signals import TimingMode
from huntbot.intrabar_study import SLIPPAGES, TimingStudyResult, evaluate_recommendation, run_key


D = Decimal


def trade(action: str, minute: int) -> TimingTrade:
    timestamp = datetime(2026, 6, 1, 0, minute, tzinfo=timezone.utc)
    return TimingTrade(action, timestamp, timestamp, timestamp, D("100"), D("100"), D("100"), 50.0, D("1"), D("0"), D("0"), "sell_1")


def result(mode: TimingMode, return_pct: str, mdd: str = "5", trades=()) -> TimingBacktestResult:
    return TimingBacktestResult(
        mode=mode,
        final_value=D("3000000") * (D("1") + D(return_pct) / D("100")),
        return_pct=D(return_pct),
        max_drawdown_pct=D(mdd),
        false_intrabar_signals=1 if mode != TimingMode.COMPLETED else 0,
        emergency_exits=0,
        final_cash=D("3000000"),
        final_quantity=D("0"),
        final_phase="sell_1",
        trades=tuple(trades),
    )


def study_fixture(
    *,
    immediate_holdout: str = "12",
    completed_holdout: str = "10",
    immediate_stress: str = "13",
    completed_stress: str = "9",
    immediate_mdd: str = "5",
    hold_holdout: str = "6",
    hold_stress: str = "6",
    hold_mdd: str = "5",
    full_trades=None,
) -> TimingStudyResult:
    if full_trades is None:
        full_trades = (
            trade("sell_1", 0), trade("buy_1", 1),
            trade("sell_1", 2), trade("buy_1", 3),
        )
    runs = {}
    for segment in ("full", "training", "holdout"):
        segment_runs = {}
        for protected in (True, False):
            for slippage in SLIPPAGES:
                for mode in TimingMode:
                    value = "7"
                    if segment == "holdout" and protected:
                        if slippage == D("0.0005"):
                            value = immediate_holdout if mode == TimingMode.IMMEDIATE else completed_holdout
                        elif slippage == D("0.003"):
                            value = immediate_stress if mode == TimingMode.IMMEDIATE else completed_stress
                    mdd = immediate_mdd if mode == TimingMode.IMMEDIATE else "5"
                    if mode == TimingMode.HOLD_30S:
                        value = hold_stress if slippage == D("0.003") else hold_holdout
                        mdd = hold_mdd
                    trades = full_trades if segment == "full" and protected and slippage == D("0.0005") else ()
                    segment_runs[run_key(mode, slippage, protected=protected)] = result(mode, value, mdd, trades)
        runs[segment] = segment_runs
    recommendation, reason = evaluate_recommendation(runs)
    return TimingStudyResult(
        split_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        runs=runs,
        recommendation=recommendation,
        recommendation_reason=reason,
    )


def metadata_fixture() -> dict:
    return {
        "market": "KRW-HUNT",
        "first_second": "2026-06-01T00:00:00+00:00",
        "last_second": "2026-06-30T00:00:00+00:00",
        "second_count": 1234,
        "coverage_days": "29",
        "missing_trade_seconds": 77,
        "generated_at": "2026-07-01T00:00:00+00:00",
    }


def test_report_marks_intrabar_inconclusive_when_edge_disappears_at_point_three_percent():
    study = study_fixture(
        immediate_holdout="12",
        completed_holdout="10",
        immediate_stress="8",
        completed_stress="9",
    )

    report = render_timing_study_markdown(
        study,
        metadata_fixture() | {"coverage_days": "60"},
    )

    assert "Recommendation: **completed**" in report
    assert "advantage did not survive 0.30% slippage" in report


def test_recommendation_falls_back_to_lower_return_eligible_candidate():
    study = study_fixture(
        immediate_holdout="14",
        immediate_mdd="8",
        hold_holdout="12",
        hold_mdd="5",
        completed_holdout="10",
        immediate_stress="13",
        hold_stress="11",
        completed_stress="9",
    )

    recommendation, _ = evaluate_recommendation(study.runs)

    assert recommendation == TimingMode.HOLD_30S.value


def test_report_contains_all_matrix_and_diagnostic_sections():
    report = render_timing_study_markdown(study_fixture(), metadata_fixture())

    for heading in (
        "## Full Period (18 runs)",
        "## Training (18 runs)",
        "## Holdout (18 runs)",
        "## Cycle Concentration",
        "## Event-Level Differences",
        "## Limitations",
    ):
        assert heading in report
    assert "Missing trade seconds: `77`" in report
    assert "Fee" in report
    assert "Slippage" in report
    assert "False signals" in report


def test_json_is_ascii_deterministic_and_contains_metadata():
    study = study_fixture()
    metadata = metadata_fixture()

    payload = timing_study_to_json(study, metadata)

    assert payload == timing_study_to_json(study, metadata)
    assert '"market": "KRW-HUNT"' in payload
    payload.encode("ascii")


def test_report_is_inconclusive_when_coverage_is_under_sixty_days():
    metadata = metadata_fixture() | {"coverage_days": "59.999"}

    report = render_timing_study_markdown(study_fixture(), metadata)

    assert "Recommendation: **inconclusive**" in report
    assert "coverage is under 60 days" in report
    assert "Recommendation: **immediate**" not in report
    payload = timing_study_to_json(study_fixture(), metadata)
    assert '"recommendation": "inconclusive"' in payload


def test_report_is_inconclusive_when_any_primary_mode_has_fewer_than_two_cycles():
    one_cycle = (trade("sell_1", 0), trade("buy_1", 1))
    report = render_timing_study_markdown(
        study_fixture(full_trades=one_cycle),
        metadata_fixture() | {"coverage_days": "60"},
    )

    assert "Recommendation: **inconclusive**" in report
    assert "fewer than two completed buy/sell cycles" in report
    assert "Completed cycles: `1`" in report


def test_report_counts_completed_cycles_deterministically_from_trades():
    two_cycles = (
        trade("sell_1", 0), trade("sell_2", 1), trade("buy_1", 2), trade("buy_2", 3),
        trade("sell_1", 4), trade("buy_1", 5),
    )
    report = render_timing_study_markdown(
        study_fixture(full_trades=two_cycles),
        metadata_fixture() | {"coverage_days": "60"},
    )

    assert "Completed cycles: `2`" in report
