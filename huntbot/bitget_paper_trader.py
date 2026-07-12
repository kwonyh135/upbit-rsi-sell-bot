from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from huntbot.btc_trend_walkforward import donchian_signals
from huntbot.config import LOG_DIR, STATE_DIR
from huntbot.models import Candle


PAPER_STATE_PATH = STATE_DIR / "bitget-btc-paper.json"
PAPER_LOG_PATH = LOG_DIR / "bitget-btc-paper.log"


@dataclass(frozen=True)
class PaperConfig:
    lookback: int = 40
    initial_equity: Decimal = Decimal("3000")
    fee_rate: Decimal = Decimal("0.0006")
    slippage: Decimal = Decimal("0.0002")
    exposure: Decimal = Decimal("1")


@dataclass(frozen=True)
class PaperTrade:
    timestamp: datetime
    action: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    equity: Decimal


@dataclass(frozen=True)
class PaperState:
    cash: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    position: str = "flat"
    peak_equity: Decimal = Decimal("0")
    last_signal_timestamp: datetime | None = None
    last_candle_timestamp: datetime | None = None
    trades: tuple[PaperTrade, ...] = ()


@dataclass(frozen=True)
class PaperCycleResult:
    state: PaperState
    action: str | None
    price: Decimal | None
    equity: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    signal_timestamp: datetime | None
    target_position: str


def load_paper_state(path: Path = PAPER_STATE_PATH) -> PaperState:
    if not path.exists():
        return PaperState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PaperState(
        cash=Decimal(raw.get("cash", "0")),
        quantity=Decimal(raw.get("quantity", "0")),
        position=raw.get("position", "flat"),
        peak_equity=Decimal(raw.get("peak_equity", "0")),
        last_signal_timestamp=_parse_datetime(raw.get("last_signal_timestamp")),
        last_candle_timestamp=_parse_datetime(raw.get("last_candle_timestamp")),
        trades=tuple(
            PaperTrade(
                timestamp=_parse_datetime(item["timestamp"]) or datetime.fromtimestamp(0, tz=timezone.utc),
                action=item["action"],
                price=Decimal(item["price"]),
                quantity=Decimal(item["quantity"]),
                fee=Decimal(item["fee"]),
                equity=Decimal(item["equity"]),
            )
            for item in raw.get("trades", [])
        ),
    )


def save_paper_state(state: PaperState, path: Path = PAPER_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(asdict(state), ensure_ascii=True, indent=2, default=_json_default) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_paper_cycle(
    candles: list[Candle],
    state: PaperState,
    config: PaperConfig = PaperConfig(),
    *,
    state_path: Path = PAPER_STATE_PATH,
) -> PaperCycleResult:
    ordered = sorted(candles, key=lambda item: _as_utc(item.timestamp))
    if len(ordered) < 2:
        raise ValueError("paper trading requires at least two candles")
    current = ordered[-1]
    current_time = _as_utc(current.timestamp)
    current_price = current.close
    state = _initialized(state, config, current_price)
    signal_timestamp, target = _latest_signal(ordered, config.lookback)
    target_position = _target_position(target)
    action = None

    if signal_timestamp is not None and (
        state.last_signal_timestamp is None or signal_timestamp > state.last_signal_timestamp
    ):
        target *= config.exposure
        state, action = _apply_target(state, target, current_price, signal_timestamp, config)
        state = replace(state, last_signal_timestamp=signal_timestamp)

    equity = _equity(state, current_price)
    peak = max(state.peak_equity, equity)
    drawdown = (peak - equity) / peak * Decimal("100") if peak > 0 else Decimal("0")
    initial = config.initial_equity
    result_state = replace(state, peak_equity=peak, last_candle_timestamp=current_time)
    save_paper_state(result_state, state_path)
    return PaperCycleResult(
        state=result_state,
        action=action,
        price=current_price,
        equity=equity,
        return_pct=(equity / initial - Decimal("1")) * Decimal("100") if initial > 0 else Decimal("0"),
        max_drawdown_pct=drawdown,
        signal_timestamp=signal_timestamp,
        target_position=target_position,
    )


def append_paper_log(result: PaperCycleResult, path: Path = PAPER_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"position={result.state.position} action={result.action} price={result.price} "
        f"equity={result.equity:.4f} return_pct={result.return_pct:.4f} "
        f"mdd={result.max_drawdown_pct:.4f} signal={result.signal_timestamp}\n"
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def _initialized(state: PaperState, config: PaperConfig, price: Decimal) -> PaperState:
    if state.cash or state.quantity or state.trades:
        return state
    equity = config.initial_equity
    return replace(state, cash=equity, peak_equity=max(state.peak_equity, equity, price * state.quantity))


def _latest_signal(candles: list[Candle], lookback: int) -> tuple[datetime | None, Decimal]:
    signals = donchian_signals(candles, lookback)
    if not signals:
        return None, Decimal("0")
    timestamp = max(signals)
    return timestamp, signals[timestamp]


def _apply_target(
    state: PaperState,
    target: Decimal,
    price: Decimal,
    timestamp: datetime,
    config: PaperConfig,
) -> tuple[PaperState, str | None]:
    current_target = Decimal("1") if state.quantity > 0 else Decimal("-1") if state.quantity < 0 else Decimal("0")
    if current_target == target:
        return state, None

    trades = list(state.trades)
    cash = state.cash
    quantity = state.quantity
    actions: list[str] = []

    def set_quantity(next_quantity: Decimal, action: str) -> None:
        nonlocal cash, quantity
        delta = next_quantity - quantity
        if not delta:
            return
        execution = _execution_price(price, delta, config.slippage)
        fee = abs(delta * execution) * config.fee_rate
        cash -= delta * execution + fee
        quantity = next_quantity
        trades.append(PaperTrade(timestamp, action, execution, delta, fee, cash + quantity * price))
        actions.append(action)

    if quantity and target and (quantity > 0) != (target > 0):
        set_quantity(Decimal("0"), "close_" + ("long" if quantity > 0 else "short"))
    equity = cash + quantity * price
    next_quantity = Decimal("0") if target == 0 else target * equity / _execution_price(price, target, config.slippage)
    if target > 0:
        set_quantity(next_quantity, "open_long")
    elif target < 0:
        set_quantity(next_quantity, "open_short")
    else:
        set_quantity(Decimal("0"), "close_" + ("long" if quantity > 0 else "short"))

    position = "long" if quantity > 0 else "short" if quantity < 0 else "flat"
    return replace(state, cash=cash, quantity=quantity, position=position, trades=tuple(trades)), actions[-1] if actions else None


def _execution_price(price: Decimal, quantity_delta: Decimal, slippage: Decimal) -> Decimal:
    return price * (Decimal("1") + slippage if quantity_delta > 0 else Decimal("1") - slippage)


def _equity(state: PaperState, price: Decimal) -> Decimal:
    return state.cash + state.quantity * price


def _target_position(target: Decimal) -> str:
    if target > 0:
        return "long"
    if target < 0:
        return "short"
    return "flat"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


__all__ = [
    "PAPER_LOG_PATH",
    "PAPER_STATE_PATH",
    "PaperConfig",
    "PaperCycleResult",
    "PaperState",
    "PaperTrade",
    "append_paper_log",
    "load_paper_state",
    "run_paper_cycle",
    "save_paper_state",
]
