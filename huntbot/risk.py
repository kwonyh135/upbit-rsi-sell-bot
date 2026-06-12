from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from huntbot.config import EMERGENCY_AVG_LOSS_PCT, EMERGENCY_CONFIRMATIONS, EMERGENCY_HIGH_DROP_PCT
from huntbot.models import Candle


@dataclass(frozen=True)
class CrashRiskResult:
    risky: bool
    confirmed: bool
    confirmations: int
    reason: str | None
    high_drop_pct: Decimal | None
    average_loss_pct: Decimal | None
    data_error: str | None = None


def evaluate_crash_risk(
    *,
    minute_candles: list[Candle],
    current_price: Decimal,
    current_price_timestamp: datetime,
    average_buy_price: Decimal,
    previous_confirmations: int,
    now: datetime,
) -> CrashRiskResult:
    if current_price <= 0:
        return _data_error("invalid_current_price", previous_confirmations)
    if now - current_price_timestamp > timedelta(minutes=2):
        return _data_error("stale_current_price", previous_confirmations)

    window_start = now - timedelta(minutes=5)
    recent = [
        candle
        for candle in minute_candles
        if window_start <= candle.timestamp <= now
    ]
    recent_high = max([current_price, *(candle.high for candle in recent)])
    high_drop_pct = _percentage_drop(recent_high, current_price)
    average_loss_pct = None
    if average_buy_price > 0:
        average_loss_pct = _percentage_drop(average_buy_price, current_price)

    high_risk = high_drop_pct >= EMERGENCY_HIGH_DROP_PCT
    average_risk = average_loss_pct is not None and average_loss_pct >= EMERGENCY_AVG_LOSS_PCT
    risky = high_risk or average_risk
    confirmations = previous_confirmations + 1 if risky else 0
    if high_risk and average_risk:
        reason = "five_minute_high_and_average_buy_price"
    elif high_risk:
        reason = "five_minute_high"
    elif average_risk:
        reason = "average_buy_price"
    else:
        reason = None
    return CrashRiskResult(
        risky=risky,
        confirmed=risky and confirmations >= EMERGENCY_CONFIRMATIONS,
        confirmations=confirmations,
        reason=reason,
        high_drop_pct=high_drop_pct,
        average_loss_pct=average_loss_pct,
    )


def _percentage_drop(reference: Decimal, current: Decimal) -> Decimal:
    if reference <= 0 or current >= reference:
        return Decimal("0")
    return ((reference - current) / reference * Decimal("100")).quantize(Decimal("0.01"))


def _data_error(reason: str, confirmations: int) -> CrashRiskResult:
    return CrashRiskResult(
        risky=False,
        confirmed=False,
        confirmations=0,
        reason=None,
        high_drop_pct=None,
        average_loss_pct=None,
        data_error=reason,
    )
