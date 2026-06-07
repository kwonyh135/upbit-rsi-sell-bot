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


@dataclass(frozen=True)
class SplitBuybackBacktestResult:
    unit: int
    sell_rsi_1: float
    sell_rsi_2: float
    buy_rsi_1: float
    buy_rsi_2: float
    final_return_pct: float
    final_total_value: Decimal
    sell_count: int
    buy_count: int
    remaining_quantity: Decimal
    cash: Decimal
    max_drawdown_pct: float
    events: tuple["TradeEvent", ...] = ()


@dataclass(frozen=True)
class TradeEvent:
    action: str
    timestamp: datetime
    unit: int
    rsi_value: float
    close_price: Decimal
    effective_price: Decimal
    quantity: Decimal
    cash: Decimal
    remaining_quantity: Decimal
    total_value: Decimal
