import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from huntbot.models import Candle
from huntbot.upbit_client import UpbitClient


def parse_candle(raw: dict, *, unit: int) -> Candle:
    timestamp = datetime.fromisoformat(raw["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
    return Candle(
        market=raw["market"],
        unit=unit,
        timestamp=timestamp,
        open=Decimal(str(raw["opening_price"])),
        high=Decimal(str(raw["high_price"])),
        low=Decimal(str(raw["low_price"])),
        close=Decimal(str(raw["trade_price"])),
        volume=Decimal(str(raw["candle_acc_trade_volume"])),
    )


def fetch_recent_candles(
    client: UpbitClient,
    market: str,
    *,
    unit: int,
    pages: int,
    to: str | None = None,
) -> list[Candle]:
    candles: list[Candle] = []
    for _ in range(pages):
        raw_page = client.get_minute_candles(market, unit=unit, count=200, to=to)
        if not raw_page:
            break
        candles.extend(parse_candle(item, unit=unit) for item in raw_page)
        oldest = min(item["candle_date_time_utc"] for item in raw_page)
        to = oldest
    unique = {candle.timestamp: candle for candle in candles}
    return [unique[key] for key in sorted(unique)]


def fetch_latest_candles(client: UpbitClient, market: str, *, unit: int, count: int) -> list[Candle]:
    raw = client.get_minute_candles(market, unit=unit, count=count)
    return sorted((parse_candle(item, unit=unit) for item in raw), key=lambda item: item.timestamp)


def latest_completed_candle(candles: list[Candle], *, unit: int, now: datetime) -> Candle | None:
    completed = [candle for candle in candles if candle.timestamp + timedelta(minutes=unit) <= now]
    return max(completed, key=lambda item: item.timestamp) if completed else None


def save_candle_snapshot(candles: list[Candle], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["market", "unit", "timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for candle in candles:
            writer.writerow(
                {
                    "market": candle.market,
                    "unit": candle.unit,
                    "timestamp": candle.timestamp.isoformat(),
                    "open": str(candle.open),
                    "high": str(candle.high),
                    "low": str(candle.low),
                    "close": str(candle.close),
                    "volume": str(candle.volume),
                }
            )


def load_candle_snapshot(path: Path) -> list[Candle]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        candles = [
            Candle(
                market=row["market"],
                unit=int(row["unit"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=Decimal(row["volume"]),
            )
            for row in rows
        ]
    return sorted(candles, key=lambda candle: candle.timestamp)


def latest_complete_candles(
    candles: list[Candle],
    *,
    now: datetime,
    days: int = 183,
) -> list[Candle]:
    cutoff = now - timedelta(days=days)
    return sorted(
        (
            candle
            for candle in candles
            if cutoff <= candle.timestamp and candle.timestamp + timedelta(minutes=candle.unit) <= now
        ),
        key=lambda candle: candle.timestamp,
    )


def prepare_study_candles(
    candles: list[Candle],
    *,
    now: datetime,
    preserve_snapshot: bool,
) -> list[Candle]:
    if preserve_snapshot:
        return sorted(candles, key=lambda candle: candle.timestamp)
    return latest_complete_candles(candles, now=now, days=183)
