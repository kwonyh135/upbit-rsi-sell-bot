import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from huntbot.config import MARKET, STATE_DIR
from huntbot.models import StrategyConfig
from huntbot.state import CYCLE_PATH, load_cycle, save_cycle
from huntbot.strategy import evaluate_sell_signal


LIVE_CONFIRMATION = "SELL KRW-HUNT"
BUY_CONFIRMATION = "BUY KRW-HUNT"
BUYBACK_SELL_RSI = 65.0
BUYBACK_BUY_RSI = 49.0
BUYBACK_STATE_PATH = STATE_DIR / "buyback.json"


@dataclass(frozen=True)
class WatchResult:
    action: str
    rsi_value: float | None
    holding_value: Decimal
    available_quantity: Decimal
    sell_quantity: Decimal
    order_uuid: str | None = None


@dataclass(frozen=True)
class BuybackState:
    phase: str = "ready_to_sell"
    pending_cash_krw: Decimal = Decimal("0")


def load_buyback_state(path: Path = BUYBACK_STATE_PATH) -> BuybackState:
    if not path.exists():
        return BuybackState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return BuybackState(phase=data["phase"], pending_cash_krw=Decimal(str(data["pending_cash_krw"])))


def save_buyback_state(state: BuybackState, path: Path = BUYBACK_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    payload["pending_cash_krw"] = str(state.pending_cash_krw)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_watch_once(
    *,
    client,
    strategy: StrategyConfig,
    rsi_value: float | None,
    current_price: Decimal,
    live: bool,
    confirm_phrase: str | None,
    cycle_path: Path = CYCLE_PATH,
) -> WatchResult:
    accounts = client.get_accounts()
    hunt_balance = _find_balance(accounts, "HUNT")
    holding_value = hunt_balance * current_price
    cycle = load_cycle(cycle_path)
    decision = evaluate_sell_signal(
        rsi_value=rsi_value,
        sell_rsi=strategy.sell_rsi,
        reset_rsi=strategy.reset_rsi,
        holding_value=holding_value,
        available_quantity=hunt_balance,
        cycle=cycle,
    )

    if not decision.should_sell:
        save_cycle(decision.next_cycle, cycle_path)
        return WatchResult(decision.reason, rsi_value, holding_value, hunt_balance, Decimal("0"))

    if not live:
        return WatchResult("dry_run_sell_signal", rsi_value, holding_value, hunt_balance, decision.sell_quantity)

    if confirm_phrase != LIVE_CONFIRMATION:
        return WatchResult("confirmation_required", rsi_value, holding_value, hunt_balance, decision.sell_quantity)

    chance = client.get_order_chance(strategy.market)
    ask_types = chance.get("market", {}).get("ask_types", [])
    if "market" not in ask_types:
        return WatchResult("market_sell_unsupported", rsi_value, holding_value, hunt_balance, decision.sell_quantity)

    order = client.market_sell(strategy.market, _format_decimal(decision.sell_quantity))
    save_cycle(decision.next_cycle, cycle_path)
    return WatchResult(
        "live_order_sent",
        rsi_value,
        holding_value,
        hunt_balance,
        decision.sell_quantity,
        order_uuid=order.get("uuid"),
    )


def run_buyback_watch_once(
    *,
    client,
    rsi_value: float | None,
    current_price: Decimal,
    live: bool,
    confirm_phrase: str | None,
    state: BuybackState | None = None,
    state_path: Path = BUYBACK_STATE_PATH,
) -> WatchResult:
    state = state or load_buyback_state(state_path)
    accounts = client.get_accounts()
    hunt_balance = _find_balance(accounts, "HUNT")
    krw_balance = _find_balance(accounts, "KRW")
    holding_value = hunt_balance * current_price

    if rsi_value is None:
        return WatchResult("rsi_unavailable", rsi_value, holding_value, hunt_balance, Decimal("0"))

    if state.phase == "ready_to_sell":
        if rsi_value < BUYBACK_SELL_RSI:
            return WatchResult("waiting_to_sell", rsi_value, holding_value, hunt_balance, Decimal("0"))
        sell_quantity = hunt_balance / Decimal("2")
        if not live:
            return WatchResult("dry_run_sell_signal", rsi_value, holding_value, hunt_balance, sell_quantity)
        if confirm_phrase != LIVE_CONFIRMATION:
            return WatchResult("sell_confirmation_required", rsi_value, holding_value, hunt_balance, sell_quantity)
        chance = client.get_order_chance(MARKET)
        if "market" not in chance.get("market", {}).get("ask_types", []):
            return WatchResult("market_sell_unsupported", rsi_value, holding_value, hunt_balance, sell_quantity)
        order = client.market_sell(MARKET, _format_decimal(sell_quantity))
        estimated_cash = sell_quantity * current_price
        save_buyback_state(BuybackState(phase="ready_to_buy", pending_cash_krw=estimated_cash), state_path)
        return WatchResult("live_sell_order_sent", rsi_value, holding_value, hunt_balance, sell_quantity, order.get("uuid"))

    if state.phase == "ready_to_buy":
        if rsi_value > BUYBACK_BUY_RSI:
            return WatchResult("waiting_to_buy", rsi_value, holding_value, hunt_balance, Decimal("0"))
        buy_amount = min(state.pending_cash_krw, krw_balance)
        if buy_amount <= 0:
            return WatchResult("no_pending_cash", rsi_value, holding_value, hunt_balance, Decimal("0"))
        if not live:
            return WatchResult("dry_run_buy_signal", rsi_value, holding_value, hunt_balance, buy_amount)
        if confirm_phrase != BUY_CONFIRMATION:
            return WatchResult("buy_confirmation_required", rsi_value, holding_value, hunt_balance, buy_amount)
        chance = client.get_order_chance(MARKET)
        if "price" not in chance.get("market", {}).get("bid_types", []):
            return WatchResult("market_buy_unsupported", rsi_value, holding_value, hunt_balance, buy_amount)
        order = client.market_buy(MARKET, _format_decimal(buy_amount))
        save_buyback_state(BuybackState(phase="ready_to_sell", pending_cash_krw=Decimal("0")), state_path)
        return WatchResult("live_buy_order_sent", rsi_value, holding_value, hunt_balance, buy_amount, order.get("uuid"))

    raise ValueError(f"unsupported buyback phase: {state.phase}")


def _find_balance(accounts: list[dict], currency: str) -> Decimal:
    for account in accounts:
        if account.get("currency") == currency:
            return Decimal(str(account.get("balance", "0")))
    return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
