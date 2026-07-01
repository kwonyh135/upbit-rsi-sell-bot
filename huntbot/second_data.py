import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class SecondCandle:
    market: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def parse_second_candle(raw: dict) -> SecondCandle:
    timestamp = datetime.fromisoformat(raw["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
    return SecondCandle(
        market=raw["market"],
        timestamp=timestamp,
        open=Decimal(str(raw["opening_price"])),
        high=Decimal(str(raw["high_price"])),
        low=Decimal(str(raw["low_price"])),
        close=Decimal(str(raw["trade_price"])),
        volume=Decimal(str(raw["candle_acc_trade_volume"])),
    )


def save_second_snapshot(candles: list[SecondCandle], path: Path) -> None:
    unique = {candle.timestamp: candle for candle in candles}
    ordered = [unique[key] for key in sorted(unique)]
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["market", "timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for candle in ordered:
            writer.writerow(
                {
                    "market": candle.market,
                    "timestamp": candle.timestamp.isoformat(),
                    "open": str(candle.open),
                    "high": str(candle.high),
                    "low": str(candle.low),
                    "close": str(candle.close),
                    "volume": str(candle.volume),
                }
            )
    temp_path.replace(path)


def load_second_snapshot(path: Path) -> list[SecondCandle]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        candles = [
            SecondCandle(
                market=row["market"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open=Decimal(row["open"]),
                high=Decimal(row["high"]),
                low=Decimal(row["low"]),
                close=Decimal(row["close"]),
                volume=Decimal(row["volume"]),
            )
            for row in rows
        ]
    unique = {candle.timestamp: candle for candle in candles}
    return [unique[key] for key in sorted(unique)]


def download_second_candles(
    client,
    market,
    *,
    start: datetime,
    end: datetime,
    snapshot_path: Path,
    sleep=time.sleep,
) -> list[SecondCandle]:
    saved = load_second_snapshot(snapshot_path) if snapshot_path.exists() else []
    unique = {item.timestamp: item for item in saved if start <= item.timestamp < end}
    if unique:
        newest_saved = max(unique)
        _download_backwards(
            client,
            market,
            cursor=end,
            stop_at=newest_saved,
            start=start,
            end=end,
            unique=unique,
            snapshot_path=snapshot_path,
            sleep=sleep,
        )
    _download_backwards(
        client,
        market,
        cursor=min(unique) if unique else end,
        stop_at=start,
        start=start,
        end=end,
        unique=unique,
        snapshot_path=snapshot_path,
        sleep=sleep,
    )
    save_second_snapshot(list(unique.values()), snapshot_path)
    return [unique[key] for key in sorted(unique)]


def _download_backwards(
    client,
    market: str,
    *,
    cursor: datetime,
    stop_at: datetime,
    start: datetime,
    end: datetime,
    unique: dict[datetime, SecondCandle],
    snapshot_path: Path,
    sleep,
) -> None:
    while cursor > stop_at:
        page = client.get_second_candles(market, count=200, to=cursor.isoformat())
        if not page:
            break
        parsed = [parse_second_candle(item) for item in page]
        for item in parsed:
            if start <= item.timestamp < end:
                unique[item.timestamp] = item
        next_cursor = min(item.timestamp for item in parsed)
        if next_cursor >= cursor:
            raise RuntimeError("second-candle cursor did not move backward")
        cursor = next_cursor
        save_second_snapshot(list(unique.values()), snapshot_path)
        sleep(0.12)
