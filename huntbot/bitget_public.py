from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import requests

from huntbot.market_data import load_candle_snapshot, save_candle_snapshot
from huntbot.models import Candle


@dataclass(frozen=True)
class FundingSettlement:
    timestamp: datetime
    rate: Decimal


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def complete_month_window(now: datetime) -> tuple[datetime, datetime, datetime]:
    current = _as_utc(now)
    end = datetime(current.year, current.month, 1, tzinfo=timezone.utc)
    start = _shift_months(end, -6)
    return start - timedelta(days=40), start, end


def parse_contract_candle(row: list[str]) -> Candle:
    timestamp = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
    return Candle(
        market="BTCUSDT",
        unit=5,
        timestamp=timestamp,
        open=Decimal(row[1]),
        high=Decimal(row[2]),
        low=Decimal(row[3]),
        close=Decimal(row[4]),
        volume=Decimal(row[5]),
    )


def parse_funding_settlement(raw: dict) -> FundingSettlement:
    return FundingSettlement(
        timestamp=datetime.fromtimestamp(int(raw["fundingTime"]) / 1000, tz=timezone.utc),
        rate=Decimal(str(raw["fundingRate"])),
    )


def _dedupe_funding(items: list[FundingSettlement]) -> list[FundingSettlement]:
    unique = {item.timestamp: item for item in items}
    return [unique[key] for key in sorted(unique)]


def save_funding_snapshot(items: list[FundingSettlement], path: Path) -> None:
    ordered = _dedupe_funding(items)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "rate"])
        writer.writeheader()
        for item in ordered:
            writer.writerow({"timestamp": item.timestamp.isoformat(), "rate": str(item.rate)})
    temp_path.replace(path)


def load_funding_snapshot(path: Path) -> list[FundingSettlement]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        items = [
            FundingSettlement(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                rate=Decimal(row["rate"]),
            )
            for row in rows
        ]
    return _dedupe_funding(items)


class BitgetPublicClient:
    def __init__(
        self,
        session=requests,
        base_url: str = "https://api.bitget.com",
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: dict) -> dict:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "00000":
            raise RuntimeError(f"Bitget API error: {payload.get('code')} {payload.get('msg')}")
        return payload


def _download_candle_page(
    client: BitgetPublicClient,
    *,
    cursor: datetime,
) -> list[Candle]:
    payload = client.get_json(
        "/api/v2/mix/market/history-candles",
        {
            "symbol": "BTCUSDT",
            "productType": "usdt-futures",
            "granularity": "5m",
            "limit": 200,
            "endTime": int(cursor.timestamp() * 1000),
        },
    )
    return [parse_contract_candle(row) for row in (payload.get("data") or [])]


def _download_funding_page(
    client: BitgetPublicClient,
    *,
    cursor: datetime,
) -> list[FundingSettlement]:
    payload = client.get_json(
        "/api/v2/mix/market/history-fund-rate",
        {
            "symbol": "BTCUSDT",
            "productType": "usdt-futures",
            "limit": 100,
            "endTime": int(cursor.timestamp() * 1000),
        },
    )
    return [parse_funding_settlement(row) for row in (payload.get("data") or [])]


def _merge_snapshots(
    saved: list[Candle] | list[FundingSettlement],
    *,
    start: datetime,
    end: datetime,
):
    return {item.timestamp: item for item in saved if start <= item.timestamp < end}


def download_history(
    client: BitgetPublicClient,
    *,
    start: datetime,
    end: datetime,
    candle_snapshot_path: Path,
    funding_snapshot_path: Path,
    sleep=time.sleep,
) -> tuple[list[Candle], list[FundingSettlement]]:
    start = _as_utc(start)
    end = _as_utc(end)
    if end <= start:
        raise ValueError("end must be after start")

    saved_candles = load_candle_snapshot(candle_snapshot_path) if candle_snapshot_path.exists() else []
    saved_funding = load_funding_snapshot(funding_snapshot_path) if funding_snapshot_path.exists() else []
    candle_map = _merge_snapshots(saved_candles, start=start, end=end)
    funding_map = _merge_snapshots(saved_funding, start=start, end=end)

    candle_cursor = end
    while candle_cursor > start:
        page = _download_candle_page(client, cursor=candle_cursor)
        if not page:
            break
        page_oldest = min(item.timestamp for item in page)
        if page_oldest >= candle_cursor:
            raise RuntimeError("candle pagination loop")
        for item in page:
            if start <= item.timestamp < end:
                candle_map[item.timestamp] = item
        candle_cursor = page_oldest
        save_candle_snapshot([candle_map[key] for key in sorted(candle_map)], candle_snapshot_path)
        sleep(0.12)

    funding_cursor = end
    while funding_cursor > start:
        page = _download_funding_page(client, cursor=funding_cursor)
        if not page:
            break
        page_oldest = min(item.timestamp for item in page)
        if page_oldest >= funding_cursor:
            raise RuntimeError("funding pagination loop")
        for item in page:
            if start <= item.timestamp < end:
                funding_map[item.timestamp] = item
        funding_cursor = page_oldest
        save_funding_snapshot([funding_map[key] for key in sorted(funding_map)], funding_snapshot_path)
        sleep(0.12)

    candles = [candle_map[key] for key in sorted(candle_map)]
    funding = [funding_map[key] for key in sorted(funding_map)]
    save_candle_snapshot(candles, candle_snapshot_path)
    save_funding_snapshot(funding, funding_snapshot_path)
    return candles, funding
