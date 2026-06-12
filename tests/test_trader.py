from decimal import Decimal

from huntbot.models import StrategyConfig
from huntbot.trader import (
    BUY_CONFIRMATION,
    LIVE_CONFIRMATION,
    BuybackState,
    WatchResult,
    load_buyback_state,
    required_buyback_confirmation,
    run_buyback_watch_once,
    run_watch_once,
    sync_buyback_state,
)


class FakeClient:
    def __init__(self, *, hunt_balance="1000", krw_balance="2000000"):
        self.orders = []
        self.hunt_balance = hunt_balance
        self.krw_balance = krw_balance

    def get_accounts(self):
        return [{"currency": "HUNT", "balance": self.hunt_balance}, {"currency": "KRW", "balance": self.krw_balance}]

    def get_order_chance(self, market):
        return {"market": {"ask_types": ["market"], "bid_types": ["price"], "bid": {"min_total": "5000"}}}

    def market_sell(self, market, volume):
        self.orders.append(("sell", market, volume))
        return {"uuid": "order-1", "market": market, "volume": volume}

    def market_buy(self, market, price):
        self.orders.append(("buy", market, price))
        return {"uuid": "order-2", "market": market, "price": price}


def test_buyback_live_confirmation_is_not_required_when_sell_phase_has_no_hunt():
    accounts = [{"currency": "HUNT", "balance": "0"}, {"currency": "KRW", "balance": "100000"}]
    assert required_buyback_confirmation(BuybackState(phase="sell_1"), accounts, rsi_value=60.0) is None


def test_buyback_live_confirmation_matches_action_phase():
    accounts = [{"currency": "HUNT", "balance": "1000"}, {"currency": "KRW", "balance": "100000"}]
    assert required_buyback_confirmation(BuybackState(phase="sell_1"), accounts, rsi_value=60.0) == LIVE_CONFIRMATION
    assert required_buyback_confirmation(BuybackState(phase="buy_1"), accounts, rsi_value=45.0) == BUY_CONFIRMATION


def test_buyback_live_confirmation_waits_until_rsi_threshold_is_reached():
    accounts = [{"currency": "HUNT", "balance": "1000"}, {"currency": "KRW", "balance": "100000"}]
    assert required_buyback_confirmation(BuybackState(phase="sell_1"), accounts, rsi_value=59.99) is None
    assert required_buyback_confirmation(BuybackState(phase="sell_2"), accounts, rsi_value=64.99) is None
    assert required_buyback_confirmation(BuybackState(phase="buy_1"), accounts, rsi_value=45.01) is None
    assert required_buyback_confirmation(BuybackState(phase="buy_2"), accounts, rsi_value=40.01) is None


def test_sync_buyback_state_moves_zero_hunt_sell_phase_to_buy_without_order(tmp_path):
    client = FakeClient(hunt_balance="0", krw_balance="100000")
    state_path = tmp_path / "buyback.json"
    result = sync_buyback_state(client=client, state_path=state_path)
    assert result.action == "synced_to_buy_1"
    assert result.sell_quantity == Decimal("100000")
    assert client.orders == []
    assert load_buyback_state(state_path) == BuybackState(phase="buy_1", pending_cash_krw=Decimal("100000"))


def test_sync_buyback_state_does_not_change_state_when_hunt_is_available(tmp_path):
    client = FakeClient(hunt_balance="1000", krw_balance="100000")
    state_path = tmp_path / "buyback.json"
    result = sync_buyback_state(client=client, state_path=state_path)
    assert result.action == "no_sync_hunt_available"
    assert result.sell_quantity == Decimal("0")
    assert client.orders == []
    assert not state_path.exists()


def test_dry_run_never_places_order(tmp_path):
    result = run_watch_once(
        client=FakeClient(),
        strategy=StrategyConfig("KRW-HUNT", 60, 14, 70.0, 60.0),
        rsi_value=75.0,
        current_price=Decimal("3000"),
        live=False,
        confirm_phrase=None,
        cycle_path=tmp_path / "cycle.json",
    )
    assert isinstance(result, WatchResult)
    assert result.order_uuid is None
    assert result.action == "dry_run_sell_signal"


def test_live_requires_confirmation_phrase(tmp_path):
    result = run_watch_once(
        client=FakeClient(),
        strategy=StrategyConfig("KRW-HUNT", 60, 14, 70.0, 60.0),
        rsi_value=75.0,
        current_price=Decimal("3000"),
        live=True,
        confirm_phrase="WRONG",
        cycle_path=tmp_path / "cycle.json",
    )
    assert result.action == "confirmation_required"


def test_buyback_dry_run_first_sell_signal_does_not_place_order(tmp_path):
    client = FakeClient()
    result = run_buyback_watch_once(
        client=client,
        rsi_value=60.0,
        current_price=Decimal("100"),
        live=False,
        confirm_phrase=None,
        state=BuybackState(phase="sell_1", pending_cash_krw=Decimal("0")),
        state_path=tmp_path / "buyback.json",
    )
    assert result.action == "dry_run_sell_1_signal"
    assert result.sell_quantity == Decimal("500")
    assert client.orders == []


def test_buyback_dry_run_second_sell_sells_remaining_balance(tmp_path):
    client = FakeClient(hunt_balance="500")
    result = run_buyback_watch_once(
        client=client,
        rsi_value=65.0,
        current_price=Decimal("100"),
        live=False,
        confirm_phrase=None,
        state=BuybackState(phase="sell_2", pending_cash_krw=Decimal("50000")),
        state_path=tmp_path / "buyback.json",
    )
    assert result.action == "dry_run_sell_2_signal"
    assert result.sell_quantity == Decimal("500")
    assert client.orders == []


def test_buyback_dry_run_zero_hunt_in_sell_phase_previews_buy_sync(tmp_path):
    client = FakeClient(hunt_balance="0", krw_balance="100000")
    state_path = tmp_path / "buyback.json"
    result = run_buyback_watch_once(
        client=client,
        rsi_value=46.0,
        current_price=Decimal("100"),
        live=False,
        confirm_phrase=None,
        state=BuybackState(phase="sell_1", pending_cash_krw=Decimal("0")),
        state_path=state_path,
    )
    assert result.action == "dry_run_sync_to_buy_1"
    assert result.sell_quantity == Decimal("100000")
    assert client.orders == []
    assert not state_path.exists()


def test_buyback_live_zero_hunt_in_sell_phase_moves_to_buy_without_order(tmp_path):
    client = FakeClient(hunt_balance="0", krw_balance="100000")
    state_path = tmp_path / "buyback.json"
    result = run_buyback_watch_once(
        client=client,
        rsi_value=46.0,
        current_price=Decimal("100"),
        live=True,
        confirm_phrase=None,
        state=BuybackState(phase="sell_1", pending_cash_krw=Decimal("0")),
        state_path=state_path,
    )
    assert result.action == "synced_to_buy_1"
    assert result.sell_quantity == Decimal("100000")
    assert client.orders == []
    assert load_buyback_state(state_path) == BuybackState(phase="buy_1", pending_cash_krw=Decimal("100000"))


def test_buyback_zero_hunt_sync_prefers_recorded_pending_cash(tmp_path):
    client = FakeClient(hunt_balance="0", krw_balance="200000")
    state_path = tmp_path / "buyback.json"
    result = run_buyback_watch_once(
        client=client,
        rsi_value=46.0,
        current_price=Decimal("100"),
        live=True,
        confirm_phrase=None,
        state=BuybackState(phase="sell_2", pending_cash_krw=Decimal("50000")),
        state_path=state_path,
    )
    assert result.action == "synced_to_buy_1"
    assert result.sell_quantity == Decimal("50000")
    assert client.orders == []
    assert load_buyback_state(state_path) == BuybackState(phase="buy_1", pending_cash_krw=Decimal("50000"))


def test_buyback_live_first_sell_moves_to_second_sell_phase(tmp_path):
    client = FakeClient()
    state_path = tmp_path / "buyback.json"
    result = run_buyback_watch_once(
        client=client,
        rsi_value=60.0,
        current_price=Decimal("100"),
        live=True,
        confirm_phrase="SELL KRW-HUNT",
        state=BuybackState(phase="sell_1", pending_cash_krw=Decimal("0")),
        state_path=state_path,
    )
    assert result.action == "live_sell_1_order_sent"
    assert client.orders == [("sell", "KRW-HUNT", "500")]
    assert load_buyback_state(state_path) == BuybackState(phase="sell_2", pending_cash_krw=Decimal("50000"))


def test_buyback_live_buy_uses_half_pending_cash_for_first_buy(tmp_path):
    client = FakeClient()
    state_path = tmp_path / "buyback.json"
    result = run_buyback_watch_once(
        client=client,
        rsi_value=45.0,
        current_price=Decimal("90"),
        live=True,
        confirm_phrase="BUY KRW-HUNT",
        state=BuybackState(phase="buy_1", pending_cash_krw=Decimal("100000")),
        state_path=state_path,
    )
    assert result.action == "live_buy_1_order_sent"
    assert result.order_uuid == "order-2"
    assert client.orders == [("buy", "KRW-HUNT", "50000")]
    assert load_buyback_state(state_path) == BuybackState(phase="buy_2", pending_cash_krw=Decimal("50000"))


def test_buyback_live_second_buy_uses_remaining_cash_and_resets_cycle(tmp_path):
    client = FakeClient()
    state_path = tmp_path / "buyback.json"
    result = run_buyback_watch_once(
        client=client,
        rsi_value=40.0,
        current_price=Decimal("90"),
        live=True,
        confirm_phrase="BUY KRW-HUNT",
        state=BuybackState(phase="buy_2", pending_cash_krw=Decimal("50000")),
        state_path=state_path,
    )
    assert result.action == "live_buy_2_order_sent"
    assert result.order_uuid == "order-2"
    assert client.orders == [("buy", "KRW-HUNT", "50000")]
    assert load_buyback_state(state_path) == BuybackState(phase="sell_1", pending_cash_krw=Decimal("0"))
