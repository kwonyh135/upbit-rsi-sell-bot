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
BUYBACK_SELL_RSI_1 = 60.0
BUYBACK_SELL_RSI_2 = 65.0
BUYBACK_BUY_RSI_1 = 45.0
BUYBACK_BUY_RSI_2 = 40.0
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
    phase: str = "sell_1"
    pending_cash_krw: Decimal = Decimal("0")


def load_buyback_state(path: Path = BUYBACK_STATE_PATH) -> BuybackState:
    if not path.exists():
        return BuybackState()
    data = json.loads(path.read_text(encoding="utf-8"))
    phase = data["phase"]
    if phase == "ready_to_sell":
        phase = "sell_1"
    elif phase == "ready_to_buy":
        phase = "buy_1"
    return BuybackState(phase=phase, pending_cash_krw=Decimal(str(data["pending_cash_krw"])))


def save_buyback_state(state: BuybackState, path: Path = BUYBACK_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    payload["pending_cash_krw"] = str(state.pending_cash_krw)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def required_buyback_confirmation(state: BuybackState, accounts: list[dict], *, rsi_value: float | None) -> str | None:
    if rsi_value is None:
        return None
    if state.phase == "sell_1":
        hunt_balance = _find_balance(accounts, "HUNT")
        if hunt_balance <= 0 or rsi_value < BUYBACK_SELL_RSI_1:
            return None
        return LIVE_CONFIRMATION
    if state.phase == "sell_2":
        hunt_balance = _find_balance(accounts, "HUNT")
        if hunt_balance <= 0 or rsi_value < BUYBACK_SELL_RSI_2:
            return None
        return LIVE_CONFIRMATION
    if state.phase == "buy_1" and rsi_value <= BUYBACK_BUY_RSI_1:
        return BUY_CONFIRMATION
    if state.phase == "buy_2" and rsi_value <= BUYBACK_BUY_RSI_2:
        return BUY_CONFIRMATION
    return None


def sync_buyback_state(*, client, state_path: Path = BUYBACK_STATE_PATH) -> WatchResult:
    state = load_buyback_state(state_path)
    accounts = client.get_accounts()
    hunt_balance = _find_balance(accounts, "HUNT")
    krw_balance = _find_balance(accounts, "KRW")

    if state.phase.startswith("buy"):
        return WatchResult("no_sync_already_buy_phase", None, Decimal("0"), hunt_balance, Decimal("0"))
    if hunt_balance > 0:
        return WatchResult("no_sync_hunt_available", None, Decimal("0"), hunt_balance, Decimal("0"))

    pending_cash = state.pending_cash_krw if state.pending_cash_krw > 0 else krw_balance
    if pending_cash <= 0:
        return WatchResult("no_hunt_or_buy_cash", None, Decimal("0"), hunt_balance, Decimal("0"))

    save_buyback_state(BuybackState(phase="buy_1", pending_cash_krw=pending_cash), state_path)
    return WatchResult("synced_to_buy_1", None, Decimal("0"), hunt_balance, pending_cash)


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
    accounts: list[dict] | None = None,
) -> WatchResult:
    state = state or load_buyback_state(state_path)
    accounts = accounts or client.get_accounts()
    hunt_balance = _find_balance(accounts, "HUNT")
    krw_balance = _find_balance(accounts, "KRW")
    holding_value = hunt_balance * current_price

    if rsi_value is None:
        return WatchResult("rsi_unavailable", rsi_value, holding_value, hunt_balance, Decimal("0"))

    if state.phase.startswith("sell") and hunt_balance <= 0:
        return _sync_zero_hunt_to_buy_phase(
            rsi_value=rsi_value,
            holding_value=holding_value,
            live=live,
            state=state,
            state_path=state_path,
            krw_balance=krw_balance,
        )

    if state.phase == "sell_1":
        return _run_buyback_sell_step(
            client=client,
            rsi_value=rsi_value,
            current_price=current_price,
            holding_value=holding_value,
            hunt_balance=hunt_balance,
            live=live,
            confirm_phrase=confirm_phrase,
            state=state,
            state_path=state_path,
            step="sell_1",
            threshold=BUYBACK_SELL_RSI_1,
            sell_quantity=hunt_balance / Decimal("2"),
            next_phase="sell_2",
        )

    if state.phase == "sell_2":
        return _run_buyback_sell_step(
            client=client,
            rsi_value=rsi_value,
            current_price=current_price,
            holding_value=holding_value,
            hunt_balance=hunt_balance,
            live=live,
            confirm_phrase=confirm_phrase,
            state=state,
            state_path=state_path,
            step="sell_2",
            threshold=BUYBACK_SELL_RSI_2,
            sell_quantity=hunt_balance,
            next_phase="buy_1",
        )

    if state.phase == "buy_1":
        buy_amount = min(state.pending_cash_krw / Decimal("2"), krw_balance)
        return _run_buyback_buy_step(
            client=client,
            rsi_value=rsi_value,
            holding_value=holding_value,
            hunt_balance=hunt_balance,
            live=live,
            confirm_phrase=confirm_phrase,
            state=state,
            state_path=state_path,
            step="buy_1",
            threshold=BUYBACK_BUY_RSI_1,
            buy_amount=buy_amount,
            next_phase="buy_2",
        )

    if state.phase == "buy_2":
        buy_amount = min(state.pending_cash_krw, krw_balance)
        return _run_buyback_buy_step(
            client=client,
            rsi_value=rsi_value,
            holding_value=holding_value,
            hunt_balance=hunt_balance,
            live=live,
            confirm_phrase=confirm_phrase,
            state=state,
            state_path=state_path,
            step="buy_2",
            threshold=BUYBACK_BUY_RSI_2,
            buy_amount=buy_amount,
            next_phase="sell_1",
        )

    raise ValueError(f"unsupported buyback phase: {state.phase}")


def _sync_zero_hunt_to_buy_phase(
    *,
    rsi_value: float,
    holding_value: Decimal,
    live: bool,
    state: BuybackState,
    state_path: Path,
    krw_balance: Decimal,
) -> WatchResult:
    pending_cash = state.pending_cash_krw if state.pending_cash_krw > 0 else krw_balance
    if pending_cash <= 0:
        return WatchResult("no_hunt_or_buy_cash", rsi_value, holding_value, Decimal("0"), Decimal("0"))
    next_state = BuybackState(phase="buy_1", pending_cash_krw=pending_cash)
    if not live:
        return WatchResult("dry_run_sync_to_buy_1", rsi_value, holding_value, Decimal("0"), pending_cash)
    save_buyback_state(next_state, state_path)
    return WatchResult("synced_to_buy_1", rsi_value, holding_value, Decimal("0"), pending_cash)


def _run_buyback_sell_step(
    *,
    client,
    rsi_value: float,
    current_price: Decimal,
    holding_value: Decimal,
    hunt_balance: Decimal,
    live: bool,
    confirm_phrase: str | None,
    state: BuybackState,
    state_path: Path,
    step: str,
    threshold: float,
    sell_quantity: Decimal,
    next_phase: str,
) -> WatchResult:
    if rsi_value < threshold:
        return WatchResult(f"waiting_to_{step}", rsi_value, holding_value, hunt_balance, Decimal("0"))
    if not live:
        return WatchResult(f"dry_run_{step}_signal", rsi_value, holding_value, hunt_balance, sell_quantity)
    if confirm_phrase != LIVE_CONFIRMATION:
        return WatchResult(f"{step}_confirmation_required", rsi_value, holding_value, hunt_balance, sell_quantity)
    chance = client.get_order_chance(MARKET)
    if "market" not in chance.get("market", {}).get("ask_types", []):
        return WatchResult(f"market_{step}_unsupported", rsi_value, holding_value, hunt_balance, sell_quantity)
    order = client.market_sell(MARKET, _format_decimal(sell_quantity))
    estimated_cash = state.pending_cash_krw + (sell_quantity * current_price)
    save_buyback_state(BuybackState(phase=next_phase, pending_cash_krw=estimated_cash), state_path)
    return WatchResult(f"live_{step}_order_sent", rsi_value, holding_value, hunt_balance, sell_quantity, order.get("uuid"))


def _run_buyback_buy_step(
    *,
    client,
    rsi_value: float,
    holding_value: Decimal,
    hunt_balance: Decimal,
    live: bool,
    confirm_phrase: str | None,
    state: BuybackState,
    state_path: Path,
    step: str,
    threshold: float,
    buy_amount: Decimal,
    next_phase: str,
) -> WatchResult:
    if rsi_value > threshold:
        return WatchResult(f"waiting_to_{step}", rsi_value, holding_value, hunt_balance, Decimal("0"))
    if buy_amount <= 0:
        return WatchResult("no_pending_cash", rsi_value, holding_value, hunt_balance, Decimal("0"))
    if not live:
        return WatchResult(f"dry_run_{step}_signal", rsi_value, holding_value, hunt_balance, buy_amount)
    if confirm_phrase != BUY_CONFIRMATION:
        return WatchResult(f"{step}_confirmation_required", rsi_value, holding_value, hunt_balance, buy_amount)
    chance = client.get_order_chance(MARKET)
    if "price" not in chance.get("market", {}).get("bid_types", []):
        return WatchResult(f"market_{step}_unsupported", rsi_value, holding_value, hunt_balance, buy_amount)
    order = client.market_buy(MARKET, _format_decimal(buy_amount))
    next_cash = state.pending_cash_krw - buy_amount
    if next_phase == "sell_1":
        next_cash = Decimal("0")
    save_buyback_state(BuybackState(phase=next_phase, pending_cash_krw=next_cash), state_path)
    return WatchResult(f"live_{step}_order_sent", rsi_value, holding_value, hunt_balance, buy_amount, order.get("uuid"))


def _find_balance(accounts: list[dict], currency: str) -> Decimal:
    for account in accounts:
        if account.get("currency") == currency:
            return Decimal(str(account.get("balance", "0")))
    return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
