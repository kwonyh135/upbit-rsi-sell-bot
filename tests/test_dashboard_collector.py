import json
from datetime import datetime, timezone
from decimal import Decimal

from huntbot.dashboard_collector import (
    DashboardCollector,
    classify_order,
    inspect_runtime,
)
from huntbot.dashboard_store import DashboardStore


def test_cancelled_order_with_execution_is_classified_as_trade():
    normalized = classify_order(
        {
            "uuid": "order-1",
            "identifier": "huntbot-buy_1-id",
            "side": "bid",
            "state": "cancel",
            "created_at": "2026-06-10T01:00:00+00:00",
            "executed_volume": "10",
            "paid_fee": "0.5",
            "trades": [
                {
                    "price": "100",
                    "volume": "10",
                    "funds": "1000",
                    "created_at": "2026-06-10T01:00:02+00:00",
                },
            ],
        }
    )

    assert normalized["action"] == "buy_1"
    assert normalized["side"] == "buy"
    assert normalized["executed_funds"] == Decimal("1000")
    assert normalized["average_price"] == Decimal("100")
    assert normalized["next_phase"] == "buy_2"
    assert normalized["completed_at"] == "2026-06-10T01:00:02+00:00"


def test_unfilled_cancel_and_non_bot_orders_are_ignored():
    assert classify_order(
        {
            "uuid": "order-1",
            "identifier": "huntbot-buy_1-id",
            "side": "bid",
            "state": "cancel",
            "executed_volume": "0",
            "trades": [],
        }
    ) is None
    assert classify_order(
        {
            "uuid": "order-2",
            "identifier": "manual-order",
            "side": "ask",
            "state": "done",
            "executed_volume": "1",
            "trades": [{"funds": "100", "volume": "1"}],
        }
    ) is None


class FakeHistoryClient:
    def __init__(self):
        self.closed_calls = []
        self.detail_calls = []

    def get_closed_orders(self, market, **params):
        self.closed_calls.append((market, params))
        return [
            {
                "uuid": "order-1",
                "identifier": "huntbot-sell_1-id",
            }
        ]

    def get_order(self, *, uuid=None, identifier=None):
        self.detail_calls.append(uuid)
        return {
            "uuid": uuid,
            "identifier": "huntbot-sell_1-id",
            "side": "ask",
            "state": "done",
            "created_at": "2026-06-10T01:00:00+00:00",
            "executed_volume": "2",
            "paid_fee": "0.1",
            "trades": [{"price": "110", "volume": "2", "funds": "220"}],
        }


def test_order_sync_uses_seven_day_windows_and_is_idempotent(tmp_path):
    client = FakeHistoryClient()
    store = DashboardStore(tmp_path / "dashboard.sqlite3")
    collector = DashboardCollector(client=client, store=store, sync_days=14)
    now = datetime(2026, 6, 10, tzinfo=timezone.utc)

    collector.sync_orders(now=now)
    collector.sync_orders(now=now)

    assert len(client.closed_calls) == 3
    assert client.detail_calls == ["order-1"]
    assert len(store.list_orders()) == 1


def test_runtime_health_uses_process_and_latest_log_heartbeat(tmp_path):
    state_path = tmp_path / "auto.json"
    log_path = tmp_path / "auto.log"
    state_path.write_text(
        json.dumps(
            {
                "phase": "buy_2",
                "last_completed_candle": "2026-06-10T01:00:00+00:00",
                "pending_order": None,
                "emergency_confirmations": 0,
                "emergency_reason": None,
            }
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "2026-06-10 10:00:00,000 INFO status=waiting phase=buy_2 action=None\n",
        encoding="utf-8",
    )

    runtime = inspect_runtime(
        state_path=state_path,
        log_path=log_path,
        now=datetime(2026, 6, 10, 1, 0, 20, tzinfo=timezone.utc),
        process_running=True,
    )

    assert runtime["health"] == "normal"
    assert runtime["phase"] == "buy_2"
    assert runtime["last_watch_at"] == "2026-06-10T01:00:00+00:00"


def test_collection_error_keeps_last_good_snapshot(tmp_path):
    class FailingClient:
        def get_accounts(self):
            raise RuntimeError("network")

    store = DashboardStore(tmp_path / "dashboard.sqlite3")
    store.save_account_snapshot(
        {
            "collected_at": "2026-06-10T01:00:00+00:00",
            "hunt_balance": Decimal("1"),
            "krw_balance": Decimal("2"),
            "average_buy_price": Decimal("3"),
            "best_bid": Decimal("4"),
            "rsi": 50.0,
            "account_value": Decimal("6"),
        }
    )
    collector = DashboardCollector(client=FailingClient(), store=store)

    result = collector.collect_market_snapshot(
        now=datetime(2026, 6, 10, 1, 1, tzinfo=timezone.utc)
    )

    assert result["stale"] is True
    assert result["snapshot"]["best_bid"] == Decimal("4")
    assert "network" in result["error"]


def test_order_sync_falls_back_to_log_uuids_when_closed_list_fails(tmp_path):
    class FallbackClient(FakeHistoryClient):
        def get_closed_orders(self, market, **params):
            raise RuntimeError("closed list unauthorized")

    log_path = tmp_path / "auto.log"
    log_path.write_text(
        "2026-06-10 10:00:00,000 INFO status=done phase=buy_2 "
        "action=buy_1 price=None rsi=40 risk=False reason=None "
        "uuid=11111111-1111-1111-1111-111111111111\n",
        encoding="utf-8",
    )
    client = FallbackClient()
    store = DashboardStore(tmp_path / "dashboard.sqlite3")
    collector = DashboardCollector(client=client, store=store, sync_days=14)

    stored = collector.sync_orders(
        now=datetime(2026, 6, 10, tzinfo=timezone.utc),
        log_path=log_path,
    )

    assert stored == 1
    assert len(store.list_orders()) == 1
    assert "closed list unauthorized" in store.get_meta("last_order_sync_warning")
