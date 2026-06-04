from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from huntbot.models import StrategyConfig
from huntbot.state import CYCLE_PATH, load_cycle, save_cycle
from huntbot.strategy import evaluate_sell_signal


LIVE_CONFIRMATION = "SELL KRW-HUNT"


@dataclass(frozen=True)
class WatchResult:
    action: str
    rsi_value: float | None
    holding_value: Decimal
    available_quantity: Decimal
    sell_quantity: Decimal
    order_uuid: str | None = None


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


def _find_balance(accounts: list[dict], currency: str) -> Decimal:
    for account in accounts:
        if account.get("currency") == currency:
            return Decimal(str(account.get("balance", "0")))
    return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
