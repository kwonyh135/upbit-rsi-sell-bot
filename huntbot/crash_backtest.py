from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from huntbot.indicators import rsi
from huntbot.models import Candle


@dataclass(frozen=True)
class ProtectionConfig:
    family: str
    name: str
    high_window_bars: int = 1
    high_drop_pct: Decimal = Decimal("0")
    average_loss_pct: Decimal = Decimal("0")
    confirmations: int = 1
    atr_floor_pct: Decimal = Decimal("0")
    atr_multiple: Decimal = Decimal("0")
    warning_drop_pct: Decimal = Decimal("0")
    warning_loss_pct: Decimal = Decimal("0")
    final_drop_pct: Decimal = Decimal("0")
    final_loss_pct: Decimal = Decimal("0")
    continuation_bars: int = 1


@dataclass(frozen=True)
class RecoveryConfig:
    mode: str
    name: str
    cooldown_bars: int = 0
    healthy_bars: int = 0


@dataclass(frozen=True)
class CrashEvent:
    action: str
    signal_timestamp: datetime
    timestamp: datetime
    price: Decimal
    quantity: Decimal
    cash: Decimal
    remaining_quantity: Decimal
    phase: str


@dataclass(frozen=True)
class CrashBacktestResult:
    protection_name: str
    recovery_name: str
    final_value: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    return_to_drawdown: Decimal
    emergency_exits: int
    normal_trades: int
    cash_bars: int
    max_recovery_bars: int
    false_exits: int
    final_cash: Decimal
    final_quantity: Decimal
    final_phase: str
    events: tuple[CrashEvent, ...]


@dataclass(frozen=True)
class ProtectionRisk:
    warning_risk: bool
    final_risk: bool
    high_drop_pct: Decimal
    average_loss_pct: Decimal


@dataclass(frozen=True)
class StudyCandidate:
    protection: ProtectionConfig
    recovery: RecoveryConfig
    train: CrashBacktestResult
    validation: CrashBacktestResult
    full: CrashBacktestResult
    stress_030: CrashBacktestResult
    stress_100: CrashBacktestResult
    low_touch: CrashBacktestResult


@dataclass(frozen=True)
class CrashStudyResult:
    baseline_train: CrashBacktestResult
    baseline_validation: CrashBacktestResult
    baseline_full: CrashBacktestResult
    current_reference: CrashBacktestResult
    family_winners: tuple[StudyCandidate, ...]
    recommendation: StudyCandidate


def select_strategy_action(
    phase: str,
    rsi_value: float | None,
    quantity: Decimal,
    cash: Decimal,
) -> str | None:
    if rsi_value is None:
        return None
    if rsi_value >= 65 and quantity > 0:
        return "sell_2"
    if rsi_value >= 60 and quantity > 0 and phase != "sell_2":
        return "sell_1"
    if phase == "buy_2":
        if rsi_value <= 40 and cash > 0:
            return "buy_2"
        return None
    if rsi_value <= 45 and cash > 0:
        return "buy_1"
    return None


def evaluate_protection(
    protection: ProtectionConfig,
    *,
    rolling_high: Decimal,
    current_price: Decimal,
    average_price: Decimal,
    atr_pct: Decimal,
) -> ProtectionRisk:
    high_drop = _percentage_drop(rolling_high, current_price)
    average_loss = _percentage_drop(average_price, current_price)
    if protection.family == "fixed":
        final = high_drop >= protection.high_drop_pct or average_loss >= protection.average_loss_pct
        return ProtectionRisk(final, final, high_drop, average_loss)
    if protection.family == "adaptive":
        high_limit = max(protection.high_drop_pct, protection.atr_multiple * atr_pct)
        average_limit = max(protection.average_loss_pct, protection.atr_multiple * atr_pct)
        final = high_drop >= high_limit or average_loss >= average_limit
        return ProtectionRisk(final, final, high_drop, average_loss)
    if protection.family == "staged":
        warning = high_drop >= protection.warning_drop_pct or average_loss >= protection.warning_loss_pct
        final = high_drop >= protection.final_drop_pct or average_loss >= protection.final_loss_pct
        return ProtectionRisk(warning, final, high_drop, average_loss)
    raise ValueError(f"unsupported protection family: {protection.family}")


def can_recover(
    recovery: RecoveryConfig,
    *,
    bars_halted: int,
    healthy_streak: int,
    close: Decimal,
    ema20: Decimal | None,
    rsi_value: float | None,
) -> bool:
    if recovery.mode == "permanent":
        return False
    if bars_halted < recovery.cooldown_bars:
        return False
    if recovery.mode == "manual":
        return True
    if recovery.mode != "automatic":
        raise ValueError(f"unsupported recovery mode: {recovery.mode}")
    return (
        healthy_streak >= recovery.healthy_bars
        and ema20 is not None
        and close > ema20
        and rsi_value is not None
        and rsi_value >= 45
    )


def fixed_candidates() -> tuple[ProtectionConfig, ...]:
    return tuple(
        ProtectionConfig(
            family="fixed",
            name=f"fixed-w{window}-d{drop}-l{loss}-c{confirmation}",
            high_window_bars=window,
            high_drop_pct=Decimal(drop),
            average_loss_pct=Decimal(loss),
            confirmations=confirmation,
        )
        for window in (1, 3, 6)
        for drop in (6, 7, 8, 9)
        for loss in (8, 10, 12)
        for confirmation in (1, 2, 3)
    )


def adaptive_candidates() -> tuple[ProtectionConfig, ...]:
    return tuple(
        ProtectionConfig(
            family="adaptive",
            name=f"adaptive-d{drop}-l{loss}-a{multiple}-c{confirmation}",
            high_window_bars=6,
            high_drop_pct=Decimal(drop),
            average_loss_pct=Decimal(loss),
            confirmations=confirmation,
            atr_multiple=Decimal(multiple),
        )
        for drop in (4, 5, 6)
        for loss in (8, 10, 12)
        for multiple in ("2.5", "3", "3.5")
        for confirmation in (1, 2)
    )


def staged_candidates() -> tuple[ProtectionConfig, ...]:
    return tuple(
        ProtectionConfig(
            family="staged",
            name=f"staged-w{warning}-f{final}-wl{warning_loss}-fl{final_loss}-c{continuation}",
            high_window_bars=6,
            warning_drop_pct=Decimal(warning),
            warning_loss_pct=Decimal(warning_loss),
            final_drop_pct=Decimal(final),
            final_loss_pct=Decimal(final_loss),
            continuation_bars=continuation,
        )
        for warning in (5, 6)
        for final in (7, 8, 9)
        if final > warning
        for warning_loss in (8, 10)
        for final_loss in (10, 12)
        if final_loss >= warning_loss
        for continuation in (1, 2)
    )


def recovery_candidates() -> tuple[RecoveryConfig, ...]:
    return (
        RecoveryConfig("manual", "manual-6h", cooldown_bars=72),
        RecoveryConfig("manual", "manual-24h", cooldown_bars=288),
        RecoveryConfig("manual", "manual-72h", cooldown_bars=864),
        RecoveryConfig("automatic", "auto-1h", cooldown_bars=12, healthy_bars=3),
        RecoveryConfig("automatic", "auto-3h", cooldown_bars=36, healthy_bars=6),
        RecoveryConfig("automatic", "auto-6h", cooldown_bars=72, healthy_bars=12),
        RecoveryConfig("permanent", "permanent"),
    )


def split_train_validation(candles: list[Candle]) -> tuple[list[Candle], list[Candle]]:
    if not candles:
        raise ValueError("candles are required")
    validation_start = candles[-1].timestamp - timedelta(days=61)
    train = [candle for candle in candles if candle.timestamp < validation_start]
    validation = [candle for candle in candles if candle.timestamp >= validation_start]
    if len(train) < 15 or len(validation) < 15:
        raise ValueError("training and validation periods require at least 15 candles each")
    return train, validation


def is_balanced_eligible(candidate_return: Decimal, baseline_return: Decimal) -> bool:
    if baseline_return >= 0:
        return candidate_return >= baseline_return * Decimal("0.9")
    return candidate_return >= baseline_return


def run_crash_study(candles: list[Candle], *, progress=None) -> CrashStudyResult:
    train_candles, validation_candles = split_train_validation(candles)
    baseline_train = run_crash_backtest(train_candles, protection=None, recovery=None)
    baseline_validation = run_crash_backtest(validation_candles, protection=None, recovery=None)
    baseline_full = run_crash_backtest(candles, protection=None, recovery=None)
    standard_recovery = next(item for item in recovery_candidates() if item.name == "auto-3h")
    families = {
        "fixed": fixed_candidates(),
        "adaptive": adaptive_candidates(),
        "staged": staged_candidates(),
    }
    winners: list[StudyCandidate] = []
    for family, protections in families.items():
        if progress:
            progress(f"searching {family} protection parameters")
        protection_runs = [
            (
                protection,
                run_crash_backtest(train_candles, protection=protection, recovery=standard_recovery),
            )
            for protection in protections
        ]
        shortlisted_protections = [item[0] for item in _rank_pairs(protection_runs, baseline_train)[:5]]
        recovery_runs = [
            (
                protection,
                recovery,
                run_crash_backtest(train_candles, protection=protection, recovery=recovery),
            )
            for protection in shortlisted_protections
            for recovery in recovery_candidates()
        ]
        recovery_runs.sort(key=lambda item: _result_sort_key(item[2], baseline_train))
        validation_shortlist = recovery_runs[:5]
        validated = [
            (
                protection,
                recovery,
                train_result,
                run_crash_backtest(validation_candles, protection=protection, recovery=recovery),
            )
            for protection, recovery, train_result in validation_shortlist
        ]
        validated.sort(key=lambda item: _result_sort_key(item[3], baseline_validation))
        protection, recovery, train_result, validation_result = validated[0]
        full = run_crash_backtest(candles, protection=protection, recovery=recovery)
        winners.append(
            StudyCandidate(
                protection=protection,
                recovery=recovery,
                train=train_result,
                validation=validation_result,
                full=full,
                stress_030=run_crash_backtest(
                    candles,
                    protection=protection,
                    recovery=recovery,
                    crash_slippage_rate=Decimal("0.003"),
                ),
                stress_100=run_crash_backtest(
                    candles,
                    protection=protection,
                    recovery=recovery,
                    crash_slippage_rate=Decimal("0.01"),
                ),
                low_touch=run_crash_backtest(
                    candles,
                    protection=protection,
                    recovery=recovery,
                    risk_price_mode="low",
                ),
            )
        )
    winners.sort(key=lambda item: _result_sort_key(item.validation, baseline_validation))
    current = ProtectionConfig(
        family="fixed",
        name="current-7pct-or-10pct-two-confirmations",
        high_window_bars=1,
        high_drop_pct=Decimal("7"),
        average_loss_pct=Decimal("10"),
        confirmations=2,
    )
    current_reference = run_crash_backtest(
        candles,
        protection=current,
        recovery=RecoveryConfig("permanent", "permanent"),
    )
    return CrashStudyResult(
        baseline_train=baseline_train,
        baseline_validation=baseline_validation,
        baseline_full=baseline_full,
        current_reference=current_reference,
        family_winners=tuple(winners),
        recommendation=winners[0],
    )


def _rank_pairs(
    pairs: list[tuple[ProtectionConfig, CrashBacktestResult]],
    baseline: CrashBacktestResult,
) -> list[tuple[ProtectionConfig, CrashBacktestResult]]:
    pairs.sort(key=lambda item: _result_sort_key(item[1], baseline))
    return pairs


def _result_sort_key(result: CrashBacktestResult, baseline: CrashBacktestResult) -> tuple:
    eligible = is_balanced_eligible(result.return_pct, baseline.return_pct)
    return (
        0 if eligible else 1,
        result.max_drawdown_pct,
        -result.return_to_drawdown,
        -result.return_pct,
    )


def run_crash_backtest(
    candles: list[Candle],
    *,
    protection: ProtectionConfig | None,
    recovery: RecoveryConfig | None,
    fee_rate: Decimal = Decimal("0.0005"),
    normal_slippage_rate: Decimal = Decimal("0.0005"),
    crash_slippage_rate: Decimal = Decimal("0.0005"),
    initial_krw: Decimal = Decimal("3000000"),
    risk_price_mode: str = "close",
) -> CrashBacktestResult:
    if len(candles) < 15:
        raise ValueError("at least 15 candles are required")

    quantity = initial_krw / candles[0].open
    cash = Decimal("0")
    average_price = candles[0].open
    phase = "sell_1"
    pending: tuple[str, datetime] | None = None
    events: list[CrashEvent] = []
    peak = initial_krw
    max_drawdown = Decimal("0")
    cash_bars = 0
    normal_trades = 0
    emergency_exits = 0
    risk_streak = 0
    defensive = False
    warning_active = False
    warning_bearish_streak = 0
    bars_halted = 0
    healthy_streak = 0
    underwater_bars = 0
    max_recovery_bars = 0
    rsi_values = rsi([float(candle.close) for candle in candles], period=14)
    ema_values = _ema([candle.close for candle in candles], period=20)
    atr_values = _atr(candles, period=14)

    for index, (candle, rsi_value) in enumerate(zip(candles, rsi_values)):
        if pending is not None:
            action, signal_timestamp = pending
            is_emergency = action.startswith("emergency")
            slippage = crash_slippage_rate if is_emergency else normal_slippage_rate
            price = _execution_price(candle.open, action, slippage)
            traded_quantity = Decimal("0")
            if action == "sell_1":
                traded_quantity = quantity / Decimal("2")
                cash += traded_quantity * price * (Decimal("1") - fee_rate)
                quantity -= traded_quantity
                phase = "sell_2"
            elif action == "sell_2":
                traded_quantity = quantity
                cash += traded_quantity * price * (Decimal("1") - fee_rate)
                quantity = Decimal("0")
                average_price = Decimal("0")
                phase = "buy_1"
            elif action == "emergency_sell_1":
                traded_quantity = quantity / Decimal("2")
                cash += traded_quantity * price * (Decimal("1") - fee_rate)
                quantity -= traded_quantity
                phase = "emergency_warning"
                defensive = True
                warning_active = True
                bars_halted = 0
                healthy_streak = 0
                warning_bearish_streak = 0
            elif action in {"emergency_sell", "emergency_sell_2"}:
                traded_quantity = quantity
                cash += traded_quantity * price * (Decimal("1") - fee_rate)
                quantity = Decimal("0")
                average_price = Decimal("0")
                phase = "emergency_halt"
                defensive = True
                warning_active = False
                bars_halted = 0
                healthy_streak = 0
                emergency_exits += 1
            elif action in {"buy_1", "buy_2"}:
                spend = cash / Decimal("2") if action == "buy_1" else cash
                bought = spend / (Decimal("1") + fee_rate) / price
                average_price = _weighted_average_price(quantity, average_price, bought, spend)
                quantity += bought
                cash -= spend
                traded_quantity = bought
                phase = "buy_2" if action == "buy_1" else "sell_1"
            else:
                raise ValueError(f"unsupported action: {action}")
            if not is_emergency:
                normal_trades += 1
            events.append(
                CrashEvent(
                    action=action,
                    signal_timestamp=signal_timestamp,
                    timestamp=candle.timestamp,
                    price=price,
                    quantity=traded_quantity,
                    cash=cash,
                    remaining_quantity=quantity,
                    phase=phase,
                )
            )
            pending = None

        value = cash + quantity * candle.close
        if value >= peak:
            peak = value
            underwater_bars = 0
        else:
            underwater_bars += 1
            max_recovery_bars = max(max_recovery_bars, underwater_bars)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * Decimal("100"))
        if cash > 0:
            cash_bars += 1

        risk = ProtectionRisk(False, False, Decimal("0"), Decimal("0"))
        if protection is not None:
            window_start = max(0, index - protection.high_window_bars + 1)
            rolling_high = max(item.high for item in candles[window_start:index + 1])
            risk_price = candle.low if risk_price_mode == "low" else candle.close
            atr = atr_values[index]
            atr_pct = atr / candle.close * Decimal("100") if atr is not None and candle.close > 0 else Decimal("0")
            risk = evaluate_protection(
                protection,
                rolling_high=rolling_high,
                current_price=risk_price,
                average_price=average_price,
                atr_pct=atr_pct,
            )

        if defensive:
            bars_halted += 1
            healthy_streak = 0 if risk.warning_risk or risk.final_risk else healthy_streak + 1
            if warning_active and pending is None:
                if index > 0 and candle.close < candles[index - 1].close:
                    warning_bearish_streak += 1
                else:
                    warning_bearish_streak = 0
                if quantity > 0 and (
                    risk.final_risk
                    or warning_bearish_streak >= (protection.continuation_bars if protection else 1)
                ):
                    pending = ("emergency_sell_2", candle.timestamp)
            if pending is None and recovery is not None and can_recover(
                recovery,
                bars_halted=bars_halted,
                healthy_streak=healthy_streak,
                close=candle.close,
                ema20=ema_values[index],
                rsi_value=rsi_value,
            ):
                defensive = False
                warning_active = False
                phase = "buy_1"
                risk_streak = 0

        risk_blocks_normal = False
        if not defensive and pending is None and protection is not None and quantity > 0:
            if protection.family == "staged" and risk.warning_risk:
                pending = ("emergency_sell_1", candle.timestamp)
                risk_blocks_normal = True
            elif protection.family in {"fixed", "adaptive"}:
                risk_streak = risk_streak + 1 if risk.final_risk else 0
                risk_blocks_normal = risk.final_risk
                if risk_streak >= protection.confirmations:
                    pending = ("emergency_sell", candle.timestamp)
                    risk_streak = 0

        if not defensive and pending is None and not risk_blocks_normal:
            action = select_strategy_action(phase, rsi_value, quantity, cash)
            if action is not None:
                pending = (action, candle.timestamp)

    final_value = cash + quantity * candles[-1].close
    return_pct = (final_value - initial_krw) / initial_krw * Decimal("100")
    ratio = return_pct / max_drawdown if max_drawdown > 0 else Decimal("0")
    return CrashBacktestResult(
        protection_name=protection.name if protection else "none",
        recovery_name=recovery.name if recovery else "none",
        final_value=final_value,
        return_pct=return_pct,
        max_drawdown_pct=max_drawdown,
        return_to_drawdown=ratio,
        emergency_exits=emergency_exits,
        normal_trades=normal_trades,
        cash_bars=cash_bars,
        max_recovery_bars=max_recovery_bars,
        false_exits=_count_false_exits(events, candles),
        final_cash=cash,
        final_quantity=quantity,
        final_phase=phase,
        events=tuple(events),
    )


def _execution_price(open_price: Decimal, action: str, slippage_rate: Decimal) -> Decimal:
    if action.startswith("sell") or action.startswith("emergency_sell"):
        return open_price * (Decimal("1") - slippage_rate)
    return open_price * (Decimal("1") + slippage_rate)


def _weighted_average_price(
    current_quantity: Decimal,
    current_average_price: Decimal,
    bought_quantity: Decimal,
    spend: Decimal,
) -> Decimal:
    total_quantity = current_quantity + bought_quantity
    if total_quantity == 0:
        return Decimal("0")
    return (current_quantity * current_average_price + spend) / total_quantity


def _percentage_drop(reference: Decimal, current: Decimal) -> Decimal:
    if reference <= 0 or current >= reference:
        return Decimal("0")
    return (reference - current) / reference * Decimal("100")


def _ema(values: list[Decimal], period: int) -> list[Decimal | None]:
    if not values:
        return []
    multiplier = Decimal("2") / Decimal(period + 1)
    result: list[Decimal | None] = []
    current = values[0]
    for index, value in enumerate(values):
        current = value if index == 0 else (value - current) * multiplier + current
        result.append(current if index >= period - 1 else None)
    return result


def _atr(candles: list[Candle], period: int) -> list[Decimal | None]:
    true_ranges: list[Decimal] = []
    for index, candle in enumerate(candles):
        if index == 0:
            true_ranges.append(candle.high - candle.low)
        else:
            previous_close = candles[index - 1].close
            true_ranges.append(
                max(
                    candle.high - candle.low,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            )
    result: list[Decimal | None] = [None] * len(candles)
    if len(true_ranges) < period:
        return result
    current = sum(true_ranges[:period], Decimal("0")) / Decimal(period)
    result[period - 1] = current
    for index in range(period, len(true_ranges)):
        current = (current * Decimal(period - 1) + true_ranges[index]) / Decimal(period)
        result[index] = current
    return result


def _count_false_exits(events: list[CrashEvent], candles: list[Candle]) -> int:
    index_by_timestamp = {candle.timestamp: index for index, candle in enumerate(candles)}
    count = 0
    for event in events:
        if event.action not in {"emergency_sell", "emergency_sell_2"}:
            continue
        start = index_by_timestamp.get(event.timestamp)
        if start is None:
            continue
        upper = event.price * Decimal("1.05")
        lower = event.price * Decimal("0.95")
        for candle in candles[start + 1:start + 289]:
            if candle.low <= lower:
                break
            if candle.high >= upper:
                count += 1
                break
    return count
