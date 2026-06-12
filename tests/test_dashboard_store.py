from decimal import Decimal

from huntbot.dashboard_store import DashboardStore


def _order(uuid="order-1", state="done"):
    return {
        "uuid": uuid,
        "identifier": "huntbot-buy_1-id",
        "action": "buy_1",
        "side": "buy",
        "state": state,
        "created_at": "2026-06-10T01:00:00+00:00",
        "completed_at": "2026-06-10T01:00:01+00:00",
        "executed_volume": Decimal("10"),
        "executed_funds": Decimal("1000"),
        "average_price": Decimal("100"),
        "paid_fee": Decimal("0.5"),
        "next_phase": "buy_2",
        "is_emergency": False,
    }


def test_order_uuid_upsert_is_idempotent(tmp_path):
    store = DashboardStore(tmp_path / "dashboard.sqlite3")
    store.upsert_order(_order())
    store.upsert_order(_order(state="cancel"))

    orders = store.list_orders()

    assert len(orders) == 1
    assert orders[0]["uuid"] == "order-1"
    assert orders[0]["state"] == "cancel"


def test_latest_snapshot_survives_collection_failure(tmp_path):
    store = DashboardStore(tmp_path / "dashboard.sqlite3")
    store.save_account_snapshot(
        {
            "collected_at": "2026-06-10T01:00:00+00:00",
            "hunt_balance": Decimal("10"),
            "krw_balance": Decimal("5000"),
            "average_buy_price": Decimal("95"),
            "best_bid": Decimal("100"),
            "rsi": 55.5,
            "account_value": Decimal("6000"),
        }
    )
    store.set_meta("last_error", "RuntimeError: network")

    snapshot = store.latest_account_snapshot()

    assert snapshot["best_bid"] == Decimal("100")
    assert store.get_meta("last_error") == "RuntimeError: network"
