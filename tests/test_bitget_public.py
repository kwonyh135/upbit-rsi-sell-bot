from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


def _bitget():
    import importlib

    return importlib.import_module("huntbot.bitget_public")


def test_complete_month_window_returns_six_full_months_and_warmup():
    bitget = _bitget()

    warmup, start, end = bitget.complete_month_window(datetime(2026, 7, 8, tzinfo=timezone.utc))

    assert start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert warmup == datetime(2025, 11, 22, tzinfo=timezone.utc)


def test_parse_contract_candle_uses_utc_and_decimal():
    bitget = _bitget()

    candle = bitget.parse_contract_candle(["1767225600000", "90000", "90100", "89900", "90050", "12.5", "1"])

    assert candle.market == "BTCUSDT"
    assert candle.unit == 5
    assert candle.close == Decimal("90050")
    assert candle.timestamp.tzinfo == timezone.utc


def test_parse_funding_settlement():
    bitget = _bitget()

    item = bitget.parse_funding_settlement({"fundingRate": "0.0001", "fundingTime": "1767225600000"})

    assert item.rate == Decimal("0.0001")
    assert item.timestamp.tzinfo == timezone.utc


def test_funding_snapshot_round_trip_dedupes_and_sorts(tmp_path):
    bitget = _bitget()
    path = tmp_path / "funding.csv"
    later = bitget.FundingSettlement(datetime(2026, 7, 1, 8, tzinfo=timezone.utc), Decimal("0.0002"))
    earlier = bitget.FundingSettlement(datetime(2026, 7, 1, 0, tzinfo=timezone.utc), Decimal("0.0001"))

    bitget.save_funding_snapshot([later, earlier, later], path)

    assert bitget.load_funding_snapshot(path) == [earlier, later]


def test_download_history_fetches_pages_and_persists_both_snapshots(tmp_path):
    bitget = _bitget()
    candle_snapshot = tmp_path / "candles.csv"
    funding_snapshot = tmp_path / "funding.csv"

    class FakeClient:
        def __init__(self):
            self.calls = []
            self.candle_pages = [
                {
                    "code": "00000",
                    "data": [
                        ["1767225900000", "90050", "90150", "90000", "90075", "9.0", "1"],
                        ["1767225600000", "90000", "90100", "89900", "90050", "12.5", "1"],
                    ],
                },
                {
                    "code": "00000",
                    "data": [
                        ["1767225600000", "90000", "90100", "89900", "90050", "12.5", "1"],
                    ],
                },
            ]
            self.funding_pages = [
                {
                    "code": "00000",
                    "data": [
                        {"fundingRate": "0.0001", "fundingTime": "1767225900000"},
                        {"fundingRate": "0.0000", "fundingTime": "1767225600000"},
                    ],
                },
                {
                    "code": "00000",
                    "data": [
                        {"fundingRate": "0.0000", "fundingTime": "1767225600000"},
                    ],
                },
            ]

        def get_json(self, path: str, params: dict) -> dict:
            self.calls.append((path, params))
            if path.endswith("history-candles"):
                return self.candle_pages.pop(0)
            if path.endswith("history-fund-rate"):
                return self.funding_pages.pop(0)
            raise AssertionError(f"unexpected path: {path}")

    candles, funding = bitget.download_history(
        FakeClient(),
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
        candle_snapshot_path=candle_snapshot,
        funding_snapshot_path=funding_snapshot,
        sleep=lambda _: None,
    )

    assert [item.close for item in candles] == [Decimal("90050"), Decimal("90075")]
    assert [item.rate for item in funding] == [Decimal("0.0000"), Decimal("0.0001")]
    assert candle_snapshot.exists()
    assert funding_snapshot.exists()
    assert bitget.load_candle_snapshot(candle_snapshot)[0].market == "BTCUSDT"
    assert bitget.load_funding_snapshot(funding_snapshot) == funding


def test_download_history_raises_on_pagination_loop():
    bitget = _bitget()

    class LoopingClient:
        def get_json(self, path: str, params: dict) -> dict:
            if path.endswith("history-candles"):
                return {
                    "code": "00000",
                    "data": [
                        ["1767226200000", "90100", "90200", "90000", "90150", "12.5", "1"],
                    ],
                }
            return {"code": "00000", "data": []}

    with pytest.raises(RuntimeError, match="pagination loop"):
        bitget.download_history(
            LoopingClient(),
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
            candle_snapshot_path=Path("unused-candles.csv"),
            funding_snapshot_path=Path("unused-funding.csv"),
            sleep=lambda _: None,
        )


def test_get_json_raises_runtime_error_for_bitget_code():
    bitget = _bitget()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": "40000", "msg": "bad request"}

    class Session:
        def get(self, url, params=None, timeout=None):
            return Response()

    client = bitget.BitgetPublicClient(session=Session())

    with pytest.raises(RuntimeError, match="Bitget API error: 40000 bad request"):
        client.get_json("/api/v2/mix/market/history-candles", {"symbol": "BTCUSDT"})
