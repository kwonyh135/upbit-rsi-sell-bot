from decimal import Decimal

from huntbot.models import StrategyConfig
from huntbot.trader import BuybackState, WatchResult, run_buyback_watch_once, run_watch_once


class FakeClient:
    def __init__(self):
        self.orders = []

    def get_accounts(self):
        return [{"currency": "HUNT", "balance": "1000"}, {"currency": "KRW", "balance": "2000000"}]

    def get_order_chance(self, market):
        return {"market": {"ask_types": ["market"], "bid_types": ["price"], "bid": {"min_total": "5000"}}}

    def market_sell(self, market, volume):
        self.orders.append(("sell", market, volume))
        return {"uuid": "order-1", "market": market, "volume": volume}

    def market_buy(self, market, price):
        self.orders.append(("buy", market, price))
        return {"uuid": "order-2", "market": market, "price": price}


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


def test_buyback_dry_run_sell_signal_does_not_place_order(tmp_path):
    client = FakeClient()
    result = run_buyback_watch_once(
        client=client,
        rsi_value=66.0,
        current_price=Decimal("100"),
        live=False,
        confirm_phrase=None,
        state=BuybackState(phase="ready_to_sell", pending_cash_krw=Decimal("0")),
        state_path=tmp_path / "buyback.json",
    )
    assert result.action == "dry_run_sell_signal"
    assert result.sell_quantity == Decimal("500")
    assert client.orders == []


def test_buyback_live_sell_requires_sell_confirmation(tmp_path):
    client = FakeClient()
    result = run_buyback_watch_once(
        client=client,
        rsi_value=66.0,
        current_price=Decimal("100"),
        live=True,
        confirm_phrase="WRONG",
        state=BuybackState(phase="ready_to_sell", pending_cash_krw=Decimal("0")),
        state_path=tmp_path / "buyback.json",
    )
    assert result.action == "sell_confirmation_required"
    assert client.orders == []


def test_buyback_live_buy_uses_pending_cash_after_confirmation(tmp_path):
    client = FakeClient()
    result = run_buyback_watch_once(
        client=client,
        rsi_value=49.0,
        current_price=Decimal("90"),
        live=True,
        confirm_phrase="BUY KRW-HUNT",
        state=BuybackState(phase="ready_to_buy", pending_cash_krw=Decimal("50000")),
        state_path=tmp_path / "buyback.json",
    )
    assert result.action == "live_buy_order_sent"
    assert result.order_uuid == "order-2"
    assert client.orders == [("buy", "KRW-HUNT", "50000")]
