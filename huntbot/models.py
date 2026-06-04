from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Candle:
    market: str
    unit: int
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class StrategyConfig:
    market: str
    unit: int
    rsi_period: int
    sell_rsi: float
    reset_rsi: float


@dataclass(frozen=True)
class BacktestResult:
    unit: int
    sell_rsi: float
    reset_rsi: float
    final_return_pct: float
    final_total_value: Decimal
    sell_count: int
    remaining_quantity: Decimal
    cash: Decimal
    max_drawdown_pct: float


@dataclass(frozen=True)
class BuybackBacktestResult:
    unit: int
    sell_rsi: float
    buy_rsi: float
    final_return_pct: float
    final_total_value: Decimal
    sell_count: int
    buy_count: int
    remaining_quantity: Decimal
    cash: Decimal
    max_drawdown_pct: float
