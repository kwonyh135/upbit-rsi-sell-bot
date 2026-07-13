from dataclasses import dataclass
from decimal import Decimal


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(closes) < period + 1:
        return [None] * len(closes)

    values: list[float | None] = [None] * len(closes)
    gains: list[float] = []
    losses: list[float] = []

    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    values[period] = _rsi_from_averages(avg_gain, avg_loss)

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        values[index] = _rsi_from_averages(avg_gain, avg_loss)

    return values


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return round(100 - (100 / (1 + relative_strength)), 6)


@dataclass
class WilderRsiPreview:
    period: int = 14
    previous_close: float | None = None
    close_count: int = 0
    gain_sum: float = 0.0
    loss_sum: float = 0.0
    avg_gain: float | None = None
    avg_loss: float | None = None

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("period must be positive")

    def preview(self, candidate_close: Decimal) -> float | None:
        if self.close_count < self.period or self.previous_close is None:
            return None
        gain, loss = self._change(float(candidate_close))
        if self.close_count == self.period:
            avg_gain = (self.gain_sum + gain) / self.period
            avg_loss = (self.loss_sum + loss) / self.period
        else:
            assert self.avg_gain is not None and self.avg_loss is not None
            avg_gain = ((self.avg_gain * (self.period - 1)) + gain) / self.period
            avg_loss = ((self.avg_loss * (self.period - 1)) + loss) / self.period
        return _rsi_from_averages(avg_gain, avg_loss)

    def append(self, close: Decimal) -> None:
        value = float(close)
        if self.previous_close is not None:
            gain, loss = self._change(value)
            if self.close_count < self.period:
                self.gain_sum += gain
                self.loss_sum += loss
            elif self.close_count == self.period:
                self.avg_gain = (self.gain_sum + gain) / self.period
                self.avg_loss = (self.loss_sum + loss) / self.period
            else:
                assert self.avg_gain is not None and self.avg_loss is not None
                self.avg_gain = ((self.avg_gain * (self.period - 1)) + gain) / self.period
                self.avg_loss = ((self.avg_loss * (self.period - 1)) + loss) / self.period
        self.previous_close = value
        self.close_count += 1

    def _change(self, close: float) -> tuple[float, float]:
        assert self.previous_close is not None
        change = close - self.previous_close
        return max(change, 0.0), max(-change, 0.0)
