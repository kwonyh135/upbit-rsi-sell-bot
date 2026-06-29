from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from huntbot.crash_backtest import (
    ProtectionConfig,
    RecoveryConfig,
    can_recover,
    evaluate_protection,
    fixed_candidates,
    is_balanced_eligible,
    recovery_candidates,
    run_crash_backtest,
    run_crash_study,
    select_balanced_result,
    select_strategy_action,
    split_train_validation,
)
from huntbot.crash_reporting import render_crash_study_markdown, study_to_json
from huntbot.__main__ import build_parser
from huntbot.market_data import (
    latest_complete_candles,
    load_candle_snapshot,
    prepare_study_candles,
    save_candle_snapshot,
)
from huntbot.models import Candle


def make_candle(timestamp: datetime, price: str = "100", *, unit: int = 5) -> Candle:
    value = Decimal(price)
    return Candle(
        market="KRW-HUNT",
        unit=unit,
        timestamp=timestamp,
        open=value,
        high=value + Decimal("2"),
        low=value - Decimal("3"),
        close=value + Decimal("1"),
        volume=Decimal("123.456"),
    )


def exact_candle(timestamp: datetime, close: str, *, open_price: str | None = None) -> Candle:
    price = Decimal(close)
    return Candle(
        market="KRW-HUNT",
        unit=5,
        timestamp=timestamp,
        open=Decimal(open_price or close),
        high=price,
        low=price,
        close=price,
        volume=Decimal("1000"),
    )


def test_candle_snapshot_round_trip_preserves_values(tmp_path):
    candles = [make_candle(datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc), "127.25")]
    path = tmp_path / "candles.csv"

    save_candle_snapshot(candles, path)

    assert load_candle_snapshot(path) == candles


def test_latest_complete_candles_excludes_partial_future_and_old_candles():
    now = datetime(2026, 6, 29, 0, 3, tzinfo=timezone.utc)
    candles = [
        make_candle(now - timedelta(days=184)),
        make_candle(now - timedelta(days=182, minutes=3)),
        make_candle(datetime(2026, 6, 28, 23, 55, tzinfo=timezone.utc)),
        make_candle(datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc)),
        make_candle(datetime(2026, 6, 29, 0, 5, tzinfo=timezone.utc)),
    ]

    result = latest_complete_candles(candles, now=now, days=183)

    assert [item.timestamp for item in result] == [
        now - timedelta(days=182, minutes=3),
        datetime(2026, 6, 28, 23, 55, tzinfo=timezone.utc),
    ]


def test_reused_snapshot_preserves_its_original_date_range():
    now = datetime(2026, 6, 29, tzinfo=timezone.utc)
    candles = [
        make_candle(now - timedelta(days=184)),
        make_candle(now - timedelta(days=1)),
    ]

    preserved = prepare_study_candles(candles, now=now, preserve_snapshot=True)
    fresh = prepare_study_candles(candles, now=now, preserve_snapshot=False)

    assert preserved == candles
    assert fresh == [candles[1]]


def test_strategy_selection_matches_production_phase_rules():
    assert select_strategy_action("buy_2", 65.0, Decimal("10"), Decimal("1000")) == "sell_2"
    assert select_strategy_action("buy_2", 44.0, Decimal("10"), Decimal("1000")) is None
    assert select_strategy_action("buy_2", 40.0, Decimal("10"), Decimal("1000")) == "buy_2"
    assert select_strategy_action("sell_2", 62.0, Decimal("10"), Decimal("1000")) is None
    assert select_strategy_action("sell_1", 62.0, Decimal("10"), Decimal("1000")) == "sell_1"
    assert select_strategy_action("sell_2", 44.0, Decimal("10"), Decimal("1000")) == "buy_1"


def test_rsi_signal_executes_at_next_candle_open():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [make_candle(start + timedelta(minutes=5 * index), "100") for index in range(15)]
    signal = make_candle(start + timedelta(minutes=75), "200")
    next_candle = make_candle(start + timedelta(minutes=80), "180")
    next_candle = Candle(
        market=next_candle.market,
        unit=next_candle.unit,
        timestamp=next_candle.timestamp,
        open=Decimal("150"),
        high=next_candle.high,
        low=next_candle.low,
        close=next_candle.close,
        volume=next_candle.volume,
    )

    result = run_crash_backtest(
        candles + [signal, next_candle],
        protection=None,
        recovery=None,
        fee_rate=Decimal("0"),
        normal_slippage_rate=Decimal("0"),
        crash_slippage_rate=Decimal("0"),
    )

    assert result.events[0].action == "sell_2"
    assert result.events[0].signal_timestamp == signal.timestamp
    assert result.events[0].timestamp == next_candle.timestamp
    assert result.events[0].price == Decimal("150")


def test_backtest_costs_reduce_final_value():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = ["100"] * 15 + ["200", "180"]
    candles = [make_candle(start + timedelta(minutes=5 * index), close) for index, close in enumerate(closes)]
    no_cost = run_crash_backtest(
        candles,
        protection=None,
        recovery=None,
        fee_rate=Decimal("0"),
        normal_slippage_rate=Decimal("0"),
        crash_slippage_rate=Decimal("0"),
    )
    with_cost = run_crash_backtest(
        candles,
        protection=None,
        recovery=None,
        fee_rate=Decimal("0.0005"),
        normal_slippage_rate=Decimal("0.0005"),
        crash_slippage_rate=Decimal("0.003"),
    )

    assert with_cost.final_value < no_cost.final_value


def test_fixed_protection_requires_consecutive_confirmations():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = ["100"] * 15 + ["94", "100", "93", "92", "91"]
    candles = [exact_candle(start + timedelta(minutes=5 * index), close) for index, close in enumerate(closes)]
    protection = ProtectionConfig(
        family="fixed",
        name="fixed-test",
        high_window_bars=6,
        high_drop_pct=Decimal("5"),
        average_loss_pct=Decimal("50"),
        confirmations=2,
    )

    result = run_crash_backtest(
        candles,
        protection=protection,
        recovery=RecoveryConfig(mode="permanent", name="permanent"),
        fee_rate=Decimal("0"),
        normal_slippage_rate=Decimal("0"),
        crash_slippage_rate=Decimal("0"),
    )

    emergency = [event for event in result.events if event.action == "emergency_sell"]
    assert len(emergency) == 1
    assert emergency[0].signal_timestamp == candles[18].timestamp
    assert emergency[0].timestamp == candles[19].timestamp


def test_adaptive_protection_widens_threshold_when_atr_is_high():
    protection = ProtectionConfig(
        family="adaptive",
        name="adaptive-test",
        high_drop_pct=Decimal("4"),
        average_loss_pct=Decimal("10"),
        atr_multiple=Decimal("3"),
    )

    low_volatility = evaluate_protection(
        protection,
        rolling_high=Decimal("100"),
        current_price=Decimal("94"),
        average_price=Decimal("100"),
        atr_pct=Decimal("1"),
    )
    high_volatility = evaluate_protection(
        protection,
        rolling_high=Decimal("100"),
        current_price=Decimal("94"),
        average_price=Decimal("100"),
        atr_pct=Decimal("3"),
    )

    assert low_volatility.final_risk is True
    assert high_volatility.final_risk is False


def test_staged_protection_sells_half_then_remainder():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = ["100"] * 15 + ["94", "90", "89", "88"]
    candles = [exact_candle(start + timedelta(minutes=5 * index), close) for index, close in enumerate(closes)]
    protection = ProtectionConfig(
        family="staged",
        name="staged-test",
        high_window_bars=6,
        warning_drop_pct=Decimal("5"),
        warning_loss_pct=Decimal("50"),
        final_drop_pct=Decimal("8"),
        final_loss_pct=Decimal("50"),
        continuation_bars=2,
    )

    result = run_crash_backtest(
        candles,
        protection=protection,
        recovery=RecoveryConfig(mode="permanent", name="permanent"),
        fee_rate=Decimal("0"),
        normal_slippage_rate=Decimal("0"),
        crash_slippage_rate=Decimal("0"),
    )

    emergency_actions = [event.action for event in result.events if event.action.startswith("emergency")]
    assert emergency_actions == ["emergency_sell_1", "emergency_sell_2"]
    assert result.final_quantity == Decimal("0")


def test_manual_and_automatic_recovery_require_their_gates():
    manual = RecoveryConfig(mode="manual", name="manual-6h", cooldown_bars=72)
    automatic = RecoveryConfig(mode="automatic", name="auto-1h", cooldown_bars=12, healthy_bars=3)

    assert can_recover(manual, bars_halted=71, healthy_streak=99, close=Decimal("101"), ema20=Decimal("100"), rsi_value=50.0) is False
    assert can_recover(manual, bars_halted=72, healthy_streak=0, close=Decimal("90"), ema20=Decimal("100"), rsi_value=30.0) is True
    assert can_recover(automatic, bars_halted=12, healthy_streak=2, close=Decimal("101"), ema20=Decimal("100"), rsi_value=50.0) is False
    assert can_recover(automatic, bars_halted=12, healthy_streak=3, close=Decimal("99"), ema20=Decimal("100"), rsi_value=50.0) is False
    assert can_recover(automatic, bars_halted=12, healthy_streak=3, close=Decimal("101"), ema20=Decimal("100"), rsi_value=44.9) is False
    assert can_recover(automatic, bars_halted=12, healthy_streak=3, close=Decimal("101"), ema20=Decimal("100"), rsi_value=45.0) is True


def test_candidate_sets_include_three_fixed_confirmations_and_all_recovery_modes():
    assert {config.confirmations for config in fixed_candidates()} == {1, 2, 3}
    assert {config.mode for config in recovery_candidates()} == {"manual", "automatic", "permanent"}


def test_chronological_split_reserves_last_two_months():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [exact_candle(start + timedelta(days=index), "100") for index in range(183)]

    train, validation = split_train_validation(candles)

    assert train[-1].timestamp < validation[0].timestamp
    assert validation[0].timestamp == candles[-1].timestamp - timedelta(days=61)
    assert validation[-1] == candles[-1]


def test_balanced_eligibility_retains_ninety_percent_of_positive_baseline():
    assert is_balanced_eligible(Decimal("9"), Decimal("10")) is True
    assert is_balanced_eligible(Decimal("8.99"), Decimal("10")) is False
    assert is_balanced_eligible(Decimal("-5"), Decimal("-4")) is False


def test_balanced_selection_does_not_disguise_an_ineligible_fallback():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [exact_candle(start + timedelta(minutes=5 * index), "100") for index in range(15)]
    template = run_crash_backtest(candles, protection=None, recovery=None)
    baseline = replace(template, return_pct=Decimal("10"), max_drawdown_pct=Decimal("20"))
    low_drawdown_but_far_short = replace(template, return_pct=Decimal("1"), max_drawdown_pct=Decimal("5"))
    closest_to_threshold = replace(template, return_pct=Decimal("8.5"), max_drawdown_pct=Decimal("15"))

    selected, eligible = select_balanced_result(
        [low_drawdown_but_far_short, closest_to_threshold],
        baseline,
    )

    assert selected is closest_to_threshold
    assert eligible is False


def test_balanced_selection_prefers_eligible_drawdown_reduction():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [exact_candle(start + timedelta(minutes=5 * index), "100") for index in range(15)]
    template = run_crash_backtest(candles, protection=None, recovery=None)
    baseline = replace(template, return_pct=Decimal("10"), max_drawdown_pct=Decimal("20"))
    eligible_high_mdd = replace(template, return_pct=Decimal("11"), max_drawdown_pct=Decimal("18"))
    eligible_low_mdd = replace(template, return_pct=Decimal("9"), max_drawdown_pct=Decimal("12"))

    selected, eligible = select_balanced_result([eligible_high_mdd, eligible_low_mdd], baseline)

    assert selected is eligible_low_mdd
    assert eligible is True


def test_parser_accepts_read_only_crash_backtest_command():
    args = build_parser().parse_args(["backtest-crash-5m", "--snapshot", "candles.csv"])

    assert args.command == "backtest-crash-5m"
    assert args.snapshot == "candles.csv"


def test_crash_study_reports_include_required_comparison_fields():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [exact_candle(start + timedelta(days=index), "100") for index in range(183)]
    study = run_crash_study(candles)
    metadata = {
        "market": "KRW-HUNT",
        "first_candle": candles[0].timestamp.isoformat(),
        "last_candle": candles[-1].timestamp.isoformat(),
        "candle_count": len(candles),
        "missing_intervals": 0,
    }

    markdown = render_crash_study_markdown(study, metadata)
    payload = study_to_json(study, metadata)

    assert "No protection baseline" in markdown
    assert "Fixed threshold" in markdown
    assert "ATR adaptive" in markdown
    assert "Two-stage defense" in markdown
    assert "Recovery" in markdown
    assert "Return" in markdown
    assert "MDD" in markdown
    assert "Emergency exits" in markdown
    assert "Eligible" in markdown
    assert "Neighbor" in markdown
    assert "zero emergency exits" in markdown
    assert "modeling proxy" in markdown
    assert "five-minute OHLC" in markdown
    assert '"last_candle"' in payload
    assert '"recommendation"' in payload
