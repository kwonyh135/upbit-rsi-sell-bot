from decimal import Decimal

from huntbot.auto_state import AutoTradeState, PendingOrder, load_auto_state
from huntbot.auto_trader import (
    AutoAction,
    reconcile_pending_order,
    run_auto_cycle,
    select_auto_action,
    submit_auto_action,
)
from huntbot.auto_state import save_auto_state
from datetime import datetime, timedelta, timezone


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


class FakeOrderClient:
    def __init__(self, order_state="done"):
        self.order_state = order_state
        self.orders = []
        self.lookups = []

    def market_sell(self, market, volume, *, identifier=None):
        self.orders.append(("sell", market, volume, identifier))
        return {"uuid": "order-1"}

    def market_buy(self, market, price, *, identifier=None):
        self.orders.append(("buy", market, price, identifier))
        return {"uuid": "order-1"}

    def get_order(self, *, uuid=None, identifier=None):
        self.lookups.append((uuid, identifier))
        return {
            "uuid": uuid or "order-1",
            "state": self.order_state,
            "executed_volume": "100",
            "trades": [{"price": "90", "volume": "100", "funds": "9000"}],
        }


def test_confirmed_emergency_overrides_normal_buy_and_sells_all_hunt():
    action = select_auto_action(
        state=AutoTradeState(phase="buy_2"),
        rsi_value=39.0,
        candle_timestamp="2026-06-09T03:00:00+00:00",
        emergency_confirmed=True,
        emergency_reason="five_minute_high",
        hunt_balance=Decimal("1234"),
        krw_balance=Decimal("100000"),
        bid_fee=Decimal("0.0005"),
    )
    assert action.action == "emergency_sell"
    assert action.side == "sell"
    assert action.requested_amount == Decimal("1234")
    assert action.next_phase == "emergency_halt"


def test_pending_and_emergency_halt_block_all_orders():
    pending = PendingOrder("id", "buy_1", "buy_2", None, 45.0, Decimal("5000"))
    assert select_auto_action(
        state=AutoTradeState(phase="buy_1", pending_order=pending),
        rsi_value=40,
        candle_timestamp="candle",
        emergency_confirmed=True,
        emergency_reason="five_minute_high",
        hunt_balance=Decimal("100"),
        krw_balance=Decimal("10000"),
        bid_fee=Decimal("0.0005"),
    ) is None
    assert select_auto_action(
        state=AutoTradeState(phase="emergency_halt"),
        rsi_value=70,
        candle_timestamp="candle",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("100"),
        krw_balance=Decimal("10000"),
        bid_fee=Decimal("0.0005"),
    ) is None


def test_normal_split_actions_use_current_balances():
    buy_1 = select_auto_action(
        state=AutoTradeState(phase="buy_1"),
        rsi_value=45,
        candle_timestamp="c1",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("0"),
        krw_balance=Decimal("100000"),
        bid_fee=Decimal("0.0005"),
    )
    buy_2 = select_auto_action(
        state=AutoTradeState(phase="buy_2"),
        rsi_value=40,
        candle_timestamp="c2",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("0"),
        krw_balance=Decimal("100000"),
        bid_fee=Decimal("0.0005"),
    )
    sell_1 = select_auto_action(
        state=AutoTradeState(phase="sell_1"),
        rsi_value=60,
        candle_timestamp="c3",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("1000"),
        krw_balance=Decimal("0"),
        bid_fee=Decimal("0.0005"),
    )
    assert buy_1.requested_amount == Decimal("50000")
    assert buy_2.requested_amount == Decimal("100000") / Decimal("1.0005")
    assert sell_1.requested_amount == Decimal("500")


def test_buy_2_phase_sells_half_when_rsi_reaches_first_sell_threshold():
    action = select_auto_action(
        state=AutoTradeState(phase="buy_2"),
        rsi_value=60,
        candle_timestamp="c3",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("1200"),
        krw_balance=Decimal("100000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action.action == "sell_1"
    assert action.side == "sell"
    assert action.requested_amount == Decimal("600")
    assert action.next_phase == "sell_2"


def test_approved_candidate_uses_sell_thresholds_56_and_61():
    common = {
        "state": AutoTradeState(phase="sell_1"),
        "candle_timestamp": "c3",
        "emergency_confirmed": False,
        "emergency_reason": None,
        "hunt_balance": Decimal("1200"),
        "krw_balance": Decimal("0"),
        "bid_fee": Decimal("0.0005"),
    }

    assert select_auto_action(rsi_value=55.9, **common) is None

    first_sell = select_auto_action(rsi_value=56, **common)
    assert first_sell is not None
    assert first_sell.action == "sell_1"
    assert first_sell.requested_amount == Decimal("600")

    second_sell = select_auto_action(rsi_value=61, **common)
    assert second_sell is not None
    assert second_sell.action == "sell_2"
    assert second_sell.requested_amount == Decimal("1200")


def test_sell_2_phase_does_not_repeat_first_sell_below_second_threshold():
    action = select_auto_action(
        state=AutoTradeState(phase="sell_2"),
        rsi_value=60.9,
        candle_timestamp="c4",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("600"),
        krw_balance=Decimal("500000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action is None


def test_sell_2_phase_rebuys_half_available_krw_when_rsi_falls_to_45():
    action = select_auto_action(
        state=AutoTradeState(phase="sell_2"),
        rsi_value=45,
        candle_timestamp="c4",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("600"),
        krw_balance=Decimal("1500000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action.action == "buy_1"
    assert action.side == "buy"
    assert action.requested_amount == Decimal("750000")
    assert action.next_phase == "buy_2"


def test_sell_1_phase_rebuys_half_available_krw_when_rsi_falls_to_45():
    action = select_auto_action(
        state=AutoTradeState(phase="sell_1"),
        rsi_value=45,
        candle_timestamp="c4",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("600"),
        krw_balance=Decimal("1500000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action.action == "buy_1"
    assert action.side == "buy"
    assert action.requested_amount == Decimal("750000")
    assert action.next_phase == "buy_2"


def test_buy_2_phase_does_not_repeat_buy_1_between_buy_thresholds():
    action = select_auto_action(
        state=AutoTradeState(phase="buy_2"),
        rsi_value=45,
        candle_timestamp="c4",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("600"),
        krw_balance=Decimal("750000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action is None


def test_buy_1_phase_still_uses_first_buy_when_rsi_is_below_second_threshold():
    action = select_auto_action(
        state=AutoTradeState(phase="buy_1"),
        rsi_value=40,
        candle_timestamp="c4",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("600"),
        krw_balance=Decimal("1500000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action.action == "buy_1"
    assert action.requested_amount == Decimal("750000")
    assert action.next_phase == "buy_2"


def test_any_phase_uses_second_sell_when_rsi_reaches_second_sell_threshold():
    action = select_auto_action(
        state=AutoTradeState(phase="buy_1"),
        rsi_value=61,
        candle_timestamp="c5",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("600"),
        krw_balance=Decimal("1500000"),
        bid_fee=Decimal("0.0005"),
    )

    assert action.action == "sell_2"
    assert action.side == "sell"
    assert action.requested_amount == Decimal("600")
    assert action.next_phase == "buy_1"


def test_same_completed_candle_is_not_processed_twice():
    assert select_auto_action(
        state=AutoTradeState(phase="sell_1", last_completed_candle="c1"),
        rsi_value=70,
        candle_timestamp="c1",
        emergency_confirmed=False,
        emergency_reason=None,
        hunt_balance=Decimal("1000"),
        krw_balance=Decimal("0"),
        bid_fee=Decimal("0.0005"),
    ) is None


def test_submit_persists_identifier_before_order_and_reconciles_done(tmp_path):
    path = tmp_path / "auto.json"
    client = FakeOrderClient()
    notifier = FakeNotifier()
    state = AutoTradeState(phase="sell_1")
    action = AutoAction(
        action="sell_1",
        side="sell",
        requested_amount=Decimal("500"),
        next_phase="sell_2",
        candle_timestamp="c1",
        rsi_value=60,
        reason="rsi",
    )

    result = submit_auto_action(
        client=client,
        notifier=notifier,
        state=state,
        action=action,
        state_path=path,
        live=True,
    )

    saved = load_auto_state(path)
    assert result.status == "done"
    assert saved.phase == "sell_2"
    assert saved.pending_order is None
    assert saved.last_completed_candle == "c1"
    assert client.orders[0][3].startswith("huntbot-sell_1-")
    assert client.lookups == [("order-1", None)]


def test_waiting_order_remains_pending_and_blocks_resubmit(tmp_path):
    path = tmp_path / "auto.json"
    client = FakeOrderClient(order_state="wait")
    action = AutoAction("buy_1", "buy", Decimal("5000"), "buy_2", "c1", 45, "rsi")

    result = submit_auto_action(
        client=client,
        notifier=FakeNotifier(),
        state=AutoTradeState(phase="buy_1"),
        action=action,
        state_path=path,
        live=True,
    )

    assert result.status == "pending"
    assert load_auto_state(path).pending_order.uuid == "order-1"
    assert len(client.orders) == 1


def test_cancelled_market_buy_with_fills_completes_and_advances_phase(tmp_path):
    path = tmp_path / "auto.json"
    client = FakeOrderClient(order_state="cancel")
    pending = PendingOrder(
        "huntbot-buy_1-id",
        "buy_1",
        "buy_2",
        "c1",
        39.9,
        Decimal("1437547"),
        uuid="order-1",
    )
    state = AutoTradeState(phase="buy_1", pending_order=pending)
    save_auto_state(state, path)

    result = reconcile_pending_order(
        client=client,
        notifier=FakeNotifier(),
        state=state,
        state_path=path,
    )

    assert result.status == "done"
    assert result.executed_quantity == Decimal("100")
    assert load_auto_state(path).phase == "buy_2"
    assert load_auto_state(path).pending_order is None


class FakeCycleClient(FakeOrderClient):
    def __init__(self):
        super().__init__()
        self.now = datetime(2026, 6, 9, 3, 10, tzinfo=timezone.utc)
        self.five_minute_rows = [
            _raw_candle(self.now, 100, high=101),
            _raw_candle(self.now - timedelta(minutes=5), 94, high=100),
            _raw_candle(self.now - timedelta(minutes=10), 94, high=100),
            *[
                _raw_candle(self.now - timedelta(minutes=5 * index), 100)
                for index in range(3, 20)
            ],
        ]

    def get_accounts(self):
        return [
            {"currency": "HUNT", "balance": "1000", "avg_buy_price": "110"},
            {"currency": "KRW", "balance": "1000000", "avg_buy_price": "0"},
        ]

    def get_orderbook(self, market, *, count=1):
        return {
            "market": market,
            "timestamp": int(self.now.timestamp() * 1000),
            "orderbook_units": [{"bid_price": 115, "ask_price": 116}],
        }

    def get_minute_candles(self, market, *, unit, count=200, to=None):
        if unit == 1:
            raise AssertionError("live crash protection must not fetch one-minute candles")
        return self.five_minute_rows[:count]

    def get_order_chance(self, market):
        return {
            "bid_fee": "0.0005",
            "market": {
                "ask_types": ["market"],
                "bid_types": ["price"],
                "bid": {"min_total": "5000"},
                "ask": {"min_total": "5000"},
            },
        }


class SafeSignalClient(FakeCycleClient):
    def __init__(self):
        super().__init__()
        self.five_minute_rows = [
            _raw_candle(
                self.now - timedelta(minutes=5 * index),
                100,
                high=100,
            )
            for index in range(20)
        ]

    def get_accounts(self):
        return [
            {"currency": "HUNT", "balance": "0", "avg_buy_price": "0"},
            {"currency": "KRW", "balance": "100000", "avg_buy_price": "0"},
        ]


def _raw_candle(timestamp, price, high=None):
    return {
        "market": "KRW-HUNT",
        "candle_date_time_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        "opening_price": price,
        "high_price": high if high is not None else price + 1,
        "low_price": price - 1,
        "trade_price": price,
        "candle_acc_trade_volume": 1,
    }


def test_floor_price_114_submits_full_emergency_sell_before_rsi_work(tmp_path):
    path = tmp_path / "auto.json"
    client = FakeCycleClient()
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int(client.now.timestamp() * 1000),
        "orderbook_units": [{"bid_price": 114, "ask_price": 115}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    assert result.action == "emergency_sell"
    assert result.status == "done"
    assert result.risk_confirmed is True
    assert result.risk_reason == "fixed_floor_114_krw"
    assert client.orders[0][0] == "sell"
    assert client.orders[0][2] == "1000"
    assert load_auto_state(path).phase == "emergency_halt"


def test_floor_price_114_without_hunt_halts_without_submitting_order(tmp_path):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    save_auto_state(
        AutoTradeState(
            rsi_signal_action="buy_1",
            rsi_signal_started_at=client.now.isoformat(),
            rsi_signal_last_seen_at=client.now.isoformat(),
            rsi_signal_candle=client.now.isoformat(),
        ),
        path,
    )
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int(client.now.timestamp() * 1000),
        "orderbook_units": [{"bid_price": 114, "ask_price": 115}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    assert result.action == "emergency_halt_no_position"
    assert result.risk_confirmed is True
    assert result.risk_reason == "fixed_floor_114_krw"
    saved = load_auto_state(path)
    assert saved.phase == "emergency_halt"
    assert saved.rsi_signal_action is None
    assert client.orders == []


def test_floor_price_115_does_not_trigger_emergency_sell(tmp_path):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int(client.now.timestamp() * 1000),
        "orderbook_units": [{"bid_price": 115, "ask_price": 116}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    assert result.action != "emergency_sell"
    assert load_auto_state(path).phase != "emergency_halt"


def test_auto_cycle_uses_best_bid_as_current_price(tmp_path):
    path = tmp_path / "auto.json"
    client = FakeCycleClient()
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int(client.now.timestamp() * 1000),
        "orderbook_units": [{"bid_price": 116, "ask_price": 117}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=False,
        now=client.now,
    )

    assert result.current_price == Decimal("116")


def test_auto_cycle_confirms_provisional_rsi_for_thirty_seconds(tmp_path, monkeypatch):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    notifier = FakeNotifier()
    monkeypatch.setattr(
        "huntbot.auto_trader.provisional_rsi",
        lambda *args, **kwargs: 45.0,
        raising=False,
    )

    first = run_auto_cycle(
        client=client,
        notifier=notifier,
        state_path=path,
        live=False,
        now=client.now,
    )
    second = run_auto_cycle(
        client=client,
        notifier=notifier,
        state_path=path,
        live=False,
        now=client.now + timedelta(seconds=20),
    )
    mature = run_auto_cycle(
        client=client,
        notifier=notifier,
        state_path=path,
        live=False,
        now=client.now + timedelta(seconds=30),
    )

    assert [first.status, second.status, mature.status] == [
        "confirming",
        "confirming",
        "dry_run",
    ]
    assert mature.action == "buy_1"
    assert load_auto_state(path).last_completed_candle == client.now.isoformat()
    assert client.orders == []


def test_stale_orderbook_clears_rsi_confirmation(tmp_path):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    save_auto_state(
        AutoTradeState(
            rsi_signal_action="buy_1",
            rsi_signal_started_at=client.now.isoformat(),
            rsi_signal_last_seen_at=client.now.isoformat(),
            rsi_signal_candle=client.now.isoformat(),
        ),
        path,
    )
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int((client.now - timedelta(minutes=3)).timestamp() * 1000),
        "orderbook_units": [{"bid_price": 100, "ask_price": 101}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    saved = load_auto_state(path)
    assert result.status == "data_error"
    assert saved.rsi_signal_action is None
    assert saved.rsi_signal_started_at is None


def test_invalid_orderbook_price_clears_confirmation_without_signal(tmp_path):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    save_auto_state(
        AutoTradeState(
            rsi_signal_action="buy_1",
            rsi_signal_started_at=client.now.isoformat(),
            rsi_signal_last_seen_at=client.now.isoformat(),
            rsi_signal_candle=client.now.isoformat(),
        ),
        path,
    )
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int(client.now.timestamp() * 1000),
        "orderbook_units": [{"bid_price": 0, "ask_price": 0}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    assert result.status == "data_error"
    assert result.risk_reason == "invalid_current_price"
    assert load_auto_state(path).rsi_signal_action is None
    assert client.orders == []


def test_below_minimum_mature_signal_is_consumed(tmp_path, monkeypatch):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    signal_candle = client.now.isoformat()
    save_auto_state(
        AutoTradeState(
            rsi_signal_action="buy_1",
            rsi_signal_started_at=(client.now - timedelta(seconds=30)).isoformat(),
            rsi_signal_last_seen_at=(client.now - timedelta(seconds=10)).isoformat(),
            rsi_signal_candle=signal_candle,
        ),
        path,
    )
    monkeypatch.setattr(
        "huntbot.auto_trader.provisional_rsi",
        lambda *args, **kwargs: 45.0,
        raising=False,
    )
    original_chance = client.get_order_chance

    def high_minimum(market):
        chance = original_chance(market)
        chance["market"]["bid"]["min_total"] = "1000000"
        return chance

    client.get_order_chance = high_minimum

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    saved = load_auto_state(path)
    assert result.status == "below_minimum"
    assert saved.last_completed_candle == signal_candle
    assert saved.rsi_signal_action is None
    assert client.orders == []


def test_mature_live_signal_submits_once_and_advances_phase(tmp_path, monkeypatch):
    path = tmp_path / "auto.json"
    client = SafeSignalClient()
    signal_candle = client.now.isoformat()
    save_auto_state(
        AutoTradeState(
            rsi_signal_action="buy_1",
            rsi_signal_started_at=(client.now - timedelta(seconds=30)).isoformat(),
            rsi_signal_last_seen_at=(client.now - timedelta(seconds=10)).isoformat(),
            rsi_signal_candle=signal_candle,
        ),
        path,
    )
    monkeypatch.setattr(
        "huntbot.auto_trader.provisional_rsi",
        lambda *args, **kwargs: 45.0,
    )

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    saved = load_auto_state(path)
    assert result.status == "done"
    assert result.action == "buy_1"
    assert saved.phase == "buy_2"
    assert saved.last_completed_candle == signal_candle
    assert saved.rsi_signal_action is None
    assert len(client.orders) == 1


def test_emergency_halt_returns_without_repeat_notification_or_api_calls(tmp_path):
    path = tmp_path / "auto.json"
    save_auto_state(AutoTradeState(phase="emergency_halt"), path)
    client = FakeCycleClient()
    client.get_accounts = lambda: (_ for _ in ()).throw(AssertionError("accounts must not be fetched while halted"))
    notifier = FakeNotifier()

    result = run_auto_cycle(
        client=client,
        notifier=notifier,
        state_path=path,
        live=True,
        now=client.now,
    )

    assert result.status == "halted"
    assert result.phase == "emergency_halt"
    assert result.action is None
    assert notifier.messages == []
    assert client.orders == []


def test_stale_orderbook_clears_previous_emergency_metadata(tmp_path):
    path = tmp_path / "auto.json"
    save_auto_state(
        AutoTradeState(
            phase="buy_2",
            emergency_confirmations=1,
            emergency_reason="five_minute_high",
        ),
        path,
    )
    client = FakeCycleClient()
    client.get_orderbook = lambda market, count=1: {
        "market": market,
        "timestamp": int((client.now - timedelta(minutes=3)).timestamp() * 1000),
        "orderbook_units": [{"bid_price": 100, "ask_price": 101}],
    }

    result = run_auto_cycle(
        client=client,
        notifier=FakeNotifier(),
        state_path=path,
        live=True,
        now=client.now,
    )

    saved = load_auto_state(path)
    assert result.status == "data_error"
    assert result.risk_reason == "stale_current_price"
    assert saved.emergency_confirmations == 0
    assert saved.emergency_reason is None
    assert client.orders == []
