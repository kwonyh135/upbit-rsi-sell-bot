from datetime import datetime, timezone
from decimal import Decimal

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
