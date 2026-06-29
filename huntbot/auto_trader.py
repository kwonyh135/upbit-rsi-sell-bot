from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from huntbot.auto_state import AUTO_STATE_PATH, AutoTradeState, PendingOrder, load_auto_state, save_auto_state
from huntbot.config import MARKET, RSI_PERIOD
from huntbot.indicators import rsi
from huntbot.market_data import fetch_latest_candles, latest_completed_candle
from huntbot.notifier import (
    NotificationError,
    emergency_detected_message,
    order_submitted_message,
    trade_completed_message,
)
from huntbot.risk import evaluate_completed_candle_crash_risk


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
    if rsi_value >= 65 and hunt_balance > 0:
        return AutoAction("sell_2", "sell", hunt_balance, "buy_1", candle_timestamp, rsi_value, "rsi")
    if rsi_value >= 60 and hunt_balance > 0 and state.phase != "sell_2":
        return AutoAction("sell_1", "sell", hunt_balance / Decimal("2"), "sell_2", candle_timestamp, rsi_value, "rsi")
    if state.phase == "buy_2":
        if rsi_value <= 40 and krw_balance > 0:
            fee_safe_amount = krw_balance / (Decimal("1") + bid_fee)
            return AutoAction("buy_2", "buy", fee_safe_amount, "sell_1", candle_timestamp, rsi_value, "rsi")
        return None
    if rsi_value <= 45 and krw_balance > 0:
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
    average_buy_price = Decimal(str(hunt_account.get("avg_buy_price", "0")))
    krw_balance = Decimal(str(krw_account.get("balance", "0")))

    orderbook = client.get_orderbook(MARKET, count=1)
    orderbook_units = orderbook.get("orderbook_units", [])
    current_price = (
        Decimal(str(orderbook_units[0].get("bid_price", "0")))
        if orderbook_units
        else None
    )
    orderbook_timestamp = orderbook.get("timestamp")
    if current_price is None or orderbook_timestamp is None:
        return AutoCycleResult(
            "data_error",
            state.phase,
            None,
            None,
            None,
            False,
            "missing_current_price",
            None,
            None,
        )
    current_price_timestamp = datetime.fromtimestamp(
        int(orderbook_timestamp) / 1000,
        tz=timezone.utc,
    )
    if now - current_price_timestamp > timedelta(minutes=2):
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

    five_minute_candles = fetch_latest_candles(client, MARKET, unit=5, count=200)
    risk = evaluate_completed_candle_crash_risk(
        five_minute_candles=five_minute_candles,
        average_buy_price=average_buy_price,
        now=now,
    )
    state = replace(
        state,
        emergency_confirmations=risk.confirmations,
        emergency_reason=risk.reason,
    )
    save_auto_state(state, state_path)
    if risk.data_error:
        return AutoCycleResult(
            "data_error",
            state.phase,
            None,
            current_price,
            None,
            False,
            risk.data_error,
            risk.high_drop_pct,
            risk.average_loss_pct,
        )

    if risk.risky and not risk.confirmed:
        return AutoCycleResult(
            "emergency_pending",
            state.phase,
            None,
            current_price,
            None,
            False,
            risk.reason,
            risk.high_drop_pct,
            risk.average_loss_pct,
        )

    if risk.confirmed:
        _notify_safely(
            notifier,
            emergency_detected_message(
                reason=risk.reason or "unknown",
                high_drop_pct=str(risk.high_drop_pct),
                average_loss_pct=str(risk.average_loss_pct) if risk.average_loss_pct is not None else None,
            ),
        )
        if hunt_balance <= 0:
            next_state = replace(state, phase="emergency_halt", emergency_confirmations=0)
            if live:
                save_auto_state(next_state, state_path)
            return AutoCycleResult(
                "halted" if live else "dry_run",
                next_state.phase if live else state.phase,
                "emergency_halt_no_position",
                current_price,
                None,
                True,
                risk.reason,
                risk.high_drop_pct,
                risk.average_loss_pct,
            )

    completed = latest_completed_candle(five_minute_candles, unit=5, now=now)
    completed_candles = [
        candle for candle in five_minute_candles
        if completed is not None and candle.timestamp <= completed.timestamp
    ]
    rsi_value = None
    candle_timestamp = None
    if completed is not None and len(completed_candles) >= RSI_PERIOD + 1:
        rsi_value = rsi([float(candle.close) for candle in completed_candles], period=RSI_PERIOD)[-1]
        candle_timestamp = completed.timestamp.isoformat()

    chance = client.get_order_chance(MARKET)
    bid_fee = Decimal(str(chance.get("bid_fee", "0")))
    action = select_auto_action(
        state=state,
        rsi_value=rsi_value,
        candle_timestamp=candle_timestamp,
        emergency_confirmed=risk.confirmed,
        emergency_reason=risk.reason,
        hunt_balance=hunt_balance,
        krw_balance=krw_balance,
        bid_fee=bid_fee,
    )
    if action is None:
        if candle_timestamp and candle_timestamp != state.last_completed_candle:
            state = replace(state, last_completed_candle=candle_timestamp)
            save_auto_state(state, state_path)
        return AutoCycleResult(
            "waiting",
            state.phase,
            None,
            current_price,
            rsi_value,
            risk.confirmed,
            risk.reason,
            risk.high_drop_pct,
            risk.average_loss_pct,
        )
    if not _meets_minimum_order(action, current_price, chance):
        return AutoCycleResult(
            "below_minimum",
            state.phase,
            action.action,
            current_price,
            rsi_value,
            risk.confirmed,
            risk.reason,
            risk.high_drop_pct,
            risk.average_loss_pct,
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
        rsi_value,
        risk.confirmed,
        risk.reason,
        risk.high_drop_pct,
        risk.average_loss_pct,
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
