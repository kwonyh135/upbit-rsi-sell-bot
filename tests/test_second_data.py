from datetime import datetime, timezone
from decimal import Decimal

from huntbot.second_data import (
    SecondCandle,
    download_second_candles,
    load_second_snapshot,
    save_second_snapshot,
)


def second(timestamp: str, close: str) -> SecondCandle:
    price = Decimal(close)
    return SecondCandle(
        market="KRW-HUNT",
        timestamp=datetime.fromisoformat(timestamp),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1000"),
    )


def raw_second(timestamp: str, close: int) -> dict:
    return {
        "market": "KRW-HUNT",
        "candle_date_time_utc": timestamp,
        "opening_price": close,
        "high_price": close,
        "low_price": close,
        "trade_price": close,
        "candle_acc_trade_volume": "1000",
    }


class FakeSecondClient:
    def __init__(self, pages: list[list[dict]]):
        self.pages = pages
        self.calls = []

    def get_second_candles(self, market, *, count=200, to=None):
        self.calls.append({"market": market, "count": count, "to": to})
        return self.pages.pop(0) if self.pages else []


def test_second_snapshot_round_trips_and_sorts(tmp_path):
    later = second("2026-06-30T00:00:02+00:00", "102")
    earlier = second("2026-06-30T00:00:01+00:00", "101")
    path = tmp_path / "seconds.csv"

    save_second_snapshot([later, earlier, later], path)

    assert load_second_snapshot(path) == [earlier, later]


def test_download_refreshes_latest_interval_then_extends_before_oldest(tmp_path):
    path = tmp_path / "seconds.csv"
    save_second_snapshot([second("2026-06-30T00:01:00+00:00", "100")], path)
    client = FakeSecondClient(
        [
            [
                raw_second("2026-06-30T00:01:30", 101),
                raw_second("2026-06-30T00:01:00", 100),
            ],
            [raw_second("2026-06-30T00:00:30", 99)],
            [],
        ]
    )

    result = download_second_candles(
        client,
        "KRW-HUNT",
        start=datetime(2026, 6, 30, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 6, 30, 0, 2, tzinfo=timezone.utc),
        snapshot_path=path,
        sleep=lambda _: None,
    )

    assert client.calls[0]["to"].startswith("2026-06-30T00:02:00")
    assert client.calls[1]["to"].startswith("2026-06-30T00:01:00")
    assert [item.timestamp.strftime("%H:%M:%S") for item in result] == [
        "00:00:30",
        "00:01:00",
        "00:01:30",
    ]
