from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from huntbot.auto_state import AUTO_STATE_PATH, AutoTradeState, PendingOrder, load_auto_state, save_auto_state
from huntbot.config import (
    AUTO_RSI_HOLD_SECONDS,
    AUTO_RSI_MAX_GAP_SECONDS,
    BUY_RSI_1,
    BUY_RSI_2,
    EMERGENCY_FLOOR_PRICE_KRW,
    MARKET,
    RSI_PERIOD,
    SELL_RSI_1,
    SELL_RSI_2,
)
from huntbot.intrabar_signals import five_minute_bucket, provisional_rsi, threshold_action
from huntbot.live_signal import clear_rsi_confirmation, update_rsi_confirmation
from huntbot.market_data import fetch_latest_candles, latest_completed_candle
from huntbot.notifier import (
    NotificationError,
    order_submitted_message,
    trade_completed_message,
)


@dataclass(frozen=True)
class AutoAction:
    action: str
    side: str
    requested_amount: Decimal
    next_phase: str
    candle_timestamp: str | None
    rsi_value: float | None
    reason: str


@dataclass(frozen=True)
class OrderWorkflowResult:
    status: str
    state: AutoTradeState
    order_uuid: str | None = None
    executed_quantity: Decimal = Decimal("0")
    executed_funds: Decimal = Decimal("0")


@dataclass(frozen=True)
class AutoCycleResult:
    status: str
    phase: str
    action: str | None
    current_price: Decimal | None
    rsi_value: float | None
    risk_confirmed: bool
    risk_reason: str | None
    high_drop_pct: Decimal | None
    average_loss_pct: Decimal | None
    order_uuid: str | None = None


def select_auto_action(
    *,
    state: AutoTradeState,
    rsi_value: float | None,
    candle_timestamp: str | None,
    emergency_confirmed: bool,
    emergency_reason: str | None,
    hunt_balance: Decimal,
    krw_balance: Decimal,
    bid_fee: Decimal,
) -> AutoAction | None:
    if state.pending_order or state.phase == "emergency_halt":
        return None
    if emergency_confirmed and hunt_balance > 0:
        return AutoAction(
            "emergency_sell",
            "sell",
            hunt_balance,
            "emergency_halt",
            candle_timestamp,
            rsi_value,
            emergency_reason or "emergency",
        )
    if rsi_value is None or candle_timestamp is None or candle_timestamp == state.last_completed_candle:
        return None
    if rsi_value >= SELL_RSI_2 and hunt_balance > 0:
        return AutoAction("sell_2", "sell", hunt_balance, "buy_1", candle_timestamp, rsi_value, "rsi")
    if rsi_value >= SELL_RSI_1 and hunt_balance > 0 and state.phase != "sell_2":
        return AutoAction("sell_1", "sell", hunt_balance / Decimal("2"), "sell_2", candle_timestamp, rsi_value, "rsi")
    if state.phase == "buy_2":
        if rsi_value <= BUY_RSI_2 and krw_balance > 0:
            fee_safe_amount = krw_balance / (Decimal("1") + bid_fee)
            return AutoAction("buy_2", "buy", fee_safe_amount, "sell_1", candle_timestamp, rsi_value, "rsi")
        return None
    if rsi_value <= BUY_RSI_1 and krw_balance > 0:
        return AutoAction("buy_1", "buy", krw_balance / Decimal("2"), "buy_2", candle_timestamp, rsi_value, "rsi")
    return None


def submit_auto_action(
    *,
    client,
    notifier,
    state: AutoTradeState,
    action: AutoAction,
    state_path: Path = AUTO_STATE_PATH,
    live: bool,
) -> OrderWorkflowResult:
    if not live:
        dry_state = replace(
            state,
            last_completed_candle=action.candle_timestamp or state.last_completed_candle,
        )
        save_auto_state(dry_state, state_path)
        return OrderWorkflowResult("dry_run", dry_state)
    identifier = f"huntbot-{action.action}-{uuid4()}"
    pending = PendingOrder(
        identifier=identifier,
        action=action.action,
        next_phase=action.next_phase,
        candle_timestamp=action.candle_timestamp,
        rsi_value=action.rsi_value,
        requested_amount=action.requested_amount,
    )
    pending_state = replace(state, pending_order=pending)
    save_auto_state(pending_state, state_path)
    try:
        if action.side == "sell":
            order = client.market_sell(MARKET, _format_decimal(action.requested_amount), identifier=identifier)
        else:
            order = client.market_buy(MARKET, _format_decimal(action.requested_amount), identifier=identifier)
    except Exception:
        return _reconcile_after_submission_error(client, notifier, pending_state, state_path)
    order_uuid = order.get("uuid")
    pending_state = replace(pending_state, pending_order=replace(pending, uuid=order_uuid))
    save_auto_state(pending_state, state_path)
    _notify_safely(notifier, order_submitted_message(action=action.action, identifier=identifier, order_uuid=order_uuid))
    return reconcile_pending_order(client=client, notifier=notifier, state=pending_state, state_path=state_path)


def run_auto_cycle(
    *,
    client,
    notifier,
    state_path: Path = AUTO_STATE_PATH,
    live: bool,
    now: datetime | None = None,
) -> AutoCycleResult:
    now = now or datetime.now(timezone.utc)
    state = load_auto_state(state_path)
    if state.pending_order:
        workflow = reconcile_pending_order(client=client, notifier=notifier, state=state, state_path=state_path)
        return AutoCycleResult(
            status=workflow.status,
            phase=workflow.state.phase,
            action=state.pending_order.action,
            current_price=None,
            rsi_value=state.pending_order.rsi_value,
            risk_confirmed=state.pending_order.action == "emergency_sell",
            risk_reason=state.emergency_reason,
            high_drop_pct=None,
            average_loss_pct=None,
            order_uuid=workflow.order_uuid,
        )
    if state.phase == "emergency_halt":
        return AutoCycleResult(
            status="halted",
            phase=state.phase,
            action=None,
            current_price=None,
            rsi_value=None,
            risk_confirmed=False,
            risk_reason=state.emergency_reason,
            high_drop_pct=None,
            average_loss_pct=None,
        )

    accounts = client.get_accounts()
    hunt_account = _find_account(accounts, "HUNT")
    krw_account = _find_account(accounts, "KRW")
    hunt_balance = Decimal(str(hunt_account.get("balance", "0")))
    krw_balance = Decimal(str(krw_account.get("balance", "0")))

    orderbook = client.get_orderbook(MARKET, count=1)
    orderbook_units = orderbook.get("orderbook_units", [])
    current_price = (
        Decimal(str(orderbook_units[0].get("bid_price", "0")))
        if orderbook_units
        else None
    )
    orderbook_timestamp = orderbook.get("timestamp")
    if current_price is None or current_price <= 0 or orderbook_timestamp is None:
        state = clear_rsi_confirmation(state)
        save_auto_state(state, state_path)
        data_error = (
            "invalid_current_price"
            if current_price is not None and current_price <= 0
            else "missing_current_price"
        )
        return AutoCycleResult(
            "data_error",
            state.phase,
            None,
            None,
            None,
            False,
            data_error,
            None,
            None,
        )
    current_price_timestamp = datetime.fromtimestamp(
        int(orderbook_timestamp) / 1000,
        tz=timezone.utc,
    )
    if now - current_price_timestamp > timedelta(minutes=2):
        state = clear_rsi_confirmation(state)
        state = replace(state, emergency_confirmations=0, emergency_reason=None)
        save_auto_state(state, state_path)
        return AutoCycleResult(
            "data_error",
            state.phase,
            None,
            current_price,
            None,
            False,
            "stale_current_price",
            None,
            None,
        )

    if current_price <= EMERGENCY_FLOOR_PRICE_KRW:
        state = clear_rsi_confirmation(state)
        state = replace(
            state,
            emergency_confirmations=0,
            emergency_reason="fixed_floor_114_krw",
        )
        if hunt_balance <= 0:
            state = replace(state, phase="emergency_halt")
            save_auto_state(state, state_path)
            return AutoCycleResult(
                "halted",
                state.phase,
                "emergency_halt_no_position",
                current_price,
                None,
                True,
                "fixed_floor_114_krw",
                None,
                None,
            )
        action = AutoAction(
            "emergency_sell",
            "sell",
            hunt_balance,
            "emergency_halt",
            None,
            None,
            "fixed_floor_114_krw",
        )
        workflow = submit_auto_action(
            client=client,
            notifier=notifier,
            state=state,
            action=action,
            state_path=state_path,
            live=live,
        )
        return AutoCycleResult(
            workflow.status,
            workflow.state.phase,
            action.action,
            current_price,
            None,
            True,
            action.reason,
            None,
            None,
            workflow.order_uuid,
        )

    five_minute_candles = fetch_latest_candles(client, MARKET, unit=5, count=200)
    completed = latest_completed_candle(five_minute_candles, unit=5, now=now)
    completed_candles = [
        candle for candle in five_minute_candles
        if completed is not None and candle.timestamp <= completed.timestamp
    ]

    rsi_value = None
    candidate_candle = None
    candidate_action = None
    if completed is not None and len(completed_candles) >= RSI_PERIOD:
        rsi_value = provisional_rsi(
            [candle.close for candle in completed_candles],
            current_price,
            period=RSI_PERIOD,
        )
        candidate_candle = five_minute_bucket(current_price_timestamp).isoformat()
        candidate_action = threshold_action(
            state.phase,
            rsi_value,
            has_hunt=hunt_balance > 0,
            has_krw=krw_balance > 0,
        )

    state, ready_candle = update_rsi_confirmation(
        state,
        candidate_action=candidate_action,
        candidate_candle=candidate_candle,
        now=now,
        hold_seconds=AUTO_RSI_HOLD_SECONDS,
        max_gap_seconds=AUTO_RSI_MAX_GAP_SECONDS,
    )
    save_auto_state(state, state_path)
    if ready_candle is None:
        return AutoCycleResult(
            "confirming" if candidate_action is not None else "waiting",
            state.phase,
            None,
            current_price,
            rsi_value,
            False,
            None,
            None,
            None,
        )

    chance = client.get_order_chance(MARKET)
    action = select_auto_action(
        state=state,
        rsi_value=rsi_value,
        candle_timestamp=ready_candle,
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=hunt_balance,
        krw_balance=krw_balance,
        bid_fee=Decimal(str(chance.get("bid_fee", "0"))),
    )
    if action is None:
        state = clear_rsi_confirmation(state)
        save_auto_state(state, state_path)
        return AutoCycleResult(
            "waiting",
            state.phase,
            None,
            current_price,
            rsi_value,
            False,
            None,
            None,
            None,
        )
    if not _meets_minimum_order(action, current_price, chance):
        state = replace(
            clear_rsi_confirmation(state),
            last_completed_candle=ready_candle,
        )
        save_auto_state(state, state_path)
        return AutoCycleResult(
            "below_minimum",
            state.phase,
            action.action,
            current_price,
            rsi_value,
            False,
            None,
            None,
            None,
        )
    state = clear_rsi_confirmation(state)
    workflow = submit_auto_action(
        client=client,
        notifier=notifier,
        state=state,
        action=action,
        state_path=state_path,
        live=live,
    )
    return AutoCycleResult(
        workflow.status,
        workflow.state.phase,
        action.action,
        current_price,
        rsi_value,
        False,
        None,
        None,
        None,
        workflow.order_uuid,
    )


def reconcile_pending_order(
    *,
    client,
    notifier,
    state: AutoTradeState,
    state_path: Path = AUTO_STATE_PATH,
) -> OrderWorkflowResult:
    pending = state.pending_order
    if pending is None:
        return OrderWorkflowResult("no_pending", state)
    order = (
        client.get_order(uuid=pending.uuid)
        if pending.uuid
        else client.get_order(identifier=pending.identifier)
    )
    order_state = order.get("state")
    order_uuid = order.get("uuid") or pending.uuid
    if order_state == "wait" or order_state == "watch":
        updated_pending = pending if pending.uuid else replace(pending, uuid=order_uuid)
        updated_state = replace(state, pending_order=updated_pending)
        save_auto_state(updated_state, state_path)
        return OrderWorkflowResult("pending", updated_state, order_uuid)
    trades = order.get("trades", [])
    executed_volume = Decimal(str(order.get("executed_volume", "0")))
    completed_with_fills = order_state == "cancel" and (bool(trades) or executed_volume > 0)
    if order_state != "done" and not completed_with_fills:
        return OrderWorkflowResult("unresolved", state, order_uuid)

    executed_quantity = sum((Decimal(str(item.get("volume", "0"))) for item in trades), Decimal("0"))
    executed_funds = sum((Decimal(str(item.get("funds", "0"))) for item in trades), Decimal("0"))
    if not trades:
        executed_quantity = executed_volume
    average_price = executed_funds / executed_quantity if executed_quantity > 0 else Decimal("0")
    next_state = AutoTradeState(
        phase=pending.next_phase,
        last_completed_candle=pending.candle_timestamp or state.last_completed_candle,
        pending_order=None,
        emergency_confirmations=0,
        emergency_reason=None,
    )
    save_auto_state(next_state, state_path)
    _notify_safely(
        notifier,
        trade_completed_message(
            action=pending.action,
            rsi_value=pending.rsi_value,
            price=_format_decimal(average_price),
            quantity=_format_decimal(executed_quantity),
            funds=_format_decimal(executed_funds),
            order_uuid=order_uuid or "",
            next_phase=pending.next_phase,
        ),
    )
    return OrderWorkflowResult("done", next_state, order_uuid, executed_quantity, executed_funds)


def _reconcile_after_submission_error(client, notifier, state: AutoTradeState, state_path: Path) -> OrderWorkflowResult:
    try:
        return reconcile_pending_order(client=client, notifier=notifier, state=state, state_path=state_path)
    except Exception:
        return OrderWorkflowResult("submission_unknown", state)


def _notify_safely(notifier, message: str) -> None:
    if notifier is None:
        return
    try:
        notifier.send(message)
    except NotificationError:
        return


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _find_account(accounts: list[dict], currency: str) -> dict:
    return next((account for account in accounts if account.get("currency") == currency), {})


def _meets_minimum_order(action: AutoAction, current_price: Decimal, chance: dict) -> bool:
    market = chance.get("market", {})
    if action.side == "buy":
        minimum = Decimal(str(market.get("bid", {}).get("min_total", "5000")))
        return action.requested_amount >= minimum
    minimum = Decimal(str(market.get("ask", {}).get("min_total", "5000")))
    return action.requested_amount * current_price >= minimum
