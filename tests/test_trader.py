from decimal import Decimal

from huntbot.models import StrategyConfig
from huntbot.trader import WatchResult, run_watch_once


class FakeClient:
    def get_accounts(self):
        return [{"currency": "HUNT", "balance": "1000"}]

    def get_order_chance(self, market):
        return {"market": {"ask_types": ["market"], "bid": {"min_total": "5000"}}}

    def market_sell(self, market, volume):
        return {"uuid": "order-1", "market": market, "volume": volume}


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
