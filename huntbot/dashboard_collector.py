import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from huntbot.config import MARKET, RSI_PERIOD
from huntbot.indicators import rsi
from huntbot.market_data import fetch_latest_candles, latest_completed_candle


ACTION_PHASES = {
    "buy_1": "buy_2",
    "buy_2": "sell_1",
    "sell_1": "sell_2",
    "sell_2": "buy_1",
    "emergency_sell": "emergency_halt",
}
ACTION_PATTERN = re.compile(
    r"^huntbot-(buy_1|buy_2|sell_1|sell_2|emergency_sell)-"
)
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ "
    r"(?P<level>INFO|WARNING|ERROR|CRITICAL) (?P<message>.*)$"
)
UUID_PATTERN = re.compile(r"\buuid=(?P<uuid>[0-9a-fA-F-]{16,})\b")


def classify_order(order: dict) -> dict | None:
    identifier = order.get("identifier") or ""
    match = ACTION_PATTERN.match(identifier)
    if not match:
        return None
    trades = order.get("trades") or []
    executed_volume = Decimal(str(order.get("executed_volume", "0")))
    if executed_volume <= 0:
        executed_volume = sum(
            (Decimal(str(item.get("volume", "0"))) for item in trades),
            Decimal("0"),
        )
    if executed_volume <= 0:
        return None
    executed_funds = sum(
        (Decimal(str(item.get("funds", "0"))) for item in trades),
        Decimal("0"),
    )
    if executed_funds <= 0:
        executed_funds = Decimal(str(order.get("executed_funds", "0")))
    action = match.group(1)
    trade_times = [item.get("created_at") for item in trades if item.get("created_at")]
    completed_at = (
        max(trade_times)
        if trade_times
        else order.get("done_at") or order.get("created_at")
    )
    return {
        "uuid": order["uuid"],
        "identifier": identifier,
        "action": action,
        "side": "buy" if order.get("side") == "bid" else "sell",
        "state": order.get("state", ""),
        "created_at": order.get("created_at"),
        "completed_at": completed_at,
        "executed_volume": executed_volume,
        "executed_funds": executed_funds,
        "average_price": (
            executed_funds / executed_volume
            if executed_volume > 0
            else Decimal("0")
        ),
        "paid_fee": Decimal(str(order.get("paid_fee", "0"))),
        "next_phase": ACTION_PHASES[action],
        "is_emergency": action == "emergency_sell",
    }


class DashboardCollector:
    def __init__(self, *, client, store, sync_days: int = 90) -> None:
        self.client = client
        self.store = store
        self.sync_days = sync_days

    def sync_orders(
        self,
        *,
        now: datetime | None = None,
        log_path: Path | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        last_sync = self.store.get_meta("last_order_sync_at")
        start = (
            max(
                now - timedelta(days=7),
                datetime.fromisoformat(last_sync) - timedelta(minutes=5),
            )
            if last_sync
            else now - timedelta(days=self.sync_days)
        )
        stored = 0
        window_start = start
        try:
            while window_start < now:
                window_end = min(window_start + timedelta(days=7), now)
                summaries = self.client.get_closed_orders(
                    MARKET,
                    start_time=window_start.isoformat(),
                    end_time=window_end.isoformat(),
                    limit=1000,
                    order_by="asc",
                )
                for summary in summaries:
                    identifier = summary.get("identifier") or ""
                    if not ACTION_PATTERN.match(identifier):
                        continue
                    if self.store.has_order(summary["uuid"]):
                        continue
                    stored += self._store_order_uuid(summary["uuid"])
                window_start = window_end
            self.store.set_meta("last_order_sync_warning", None)
        except Exception as exc:
            if log_path is None:
                raise
            stored += self._sync_log_uuids(log_path)
            self.store.set_meta(
                "last_order_sync_warning",
                f"{type(exc).__name__}: {exc}",
            )
        self.store.set_meta("last_order_sync_at", now.isoformat())
        return stored

    def _sync_log_uuids(self, log_path: Path) -> int:
        stored = 0
        candidates = sorted(log_path.parent.glob(f"{log_path.name}*"))
        for candidate in candidates:
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in UUID_PATTERN.finditer(text):
                uuid = match.group("uuid")
                if self.store.has_order(uuid):
                    continue
                stored += self._store_order_uuid(uuid)
        return stored

    def _store_order_uuid(self, uuid: str) -> int:
        detail = self.client.get_order(uuid=uuid)
        normalized = classify_order(detail)
        if not normalized:
            return 0
        self.store.upsert_order(normalized)
        return 1

    def collect_market_snapshot(self, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        try:
            accounts = self.client.get_accounts()
            hunt = next(
                (item for item in accounts if item.get("currency") == "HUNT"),
                {},
            )
            krw = next(
                (item for item in accounts if item.get("currency") == "KRW"),
                {},
            )
            hunt_balance = Decimal(str(hunt.get("balance", "0")))
            krw_balance = Decimal(str(krw.get("balance", "0")))
            average_buy = Decimal(str(hunt.get("avg_buy_price", "0")))
            orderbook = self.client.get_orderbook(MARKET, count=1)
            units = orderbook.get("orderbook_units") or []
            if not units:
                raise RuntimeError("missing best bid")
            best_bid = Decimal(str(units[0]["bid_price"]))
            candles = fetch_latest_candles(
                self.client, MARKET, unit=5, count=200
            )
            completed = latest_completed_candle(candles, unit=5, now=now)
            completed_candles = [
                candle
                for candle in candles
                if completed is not None and candle.timestamp <= completed.timestamp
            ]
            rsi_values = (
                rsi(
                    [float(candle.close) for candle in completed_candles],
                    period=RSI_PERIOD,
                )
                if len(completed_candles) >= RSI_PERIOD + 1
                else []
            )
            latest_rsi = rsi_values[-1] if rsi_values else None
            if rsi_values:
                offset = len(completed_candles) - len(rsi_values)
                for index, value in enumerate(rsi_values):
                    candle = completed_candles[offset + index]
                    self.store.upsert_candle(
                        {
                            "timestamp": candle.timestamp.isoformat(),
                            "open": candle.open,
                            "high": candle.high,
                            "low": candle.low,
                            "close": candle.close,
                            "rsi": value,
                        }
                    )
            snapshot = {
                "collected_at": now.isoformat(),
                "hunt_balance": hunt_balance,
                "krw_balance": krw_balance,
                "average_buy_price": average_buy,
                "best_bid": best_bid,
                "rsi": latest_rsi,
                "account_value": krw_balance + hunt_balance * best_bid,
            }
            self.store.save_account_snapshot(snapshot)
            self.store.set_meta("last_success_at", now.isoformat())
            self.store.set_meta("last_error", None)
            return {"snapshot": snapshot, "stale": False, "error": None}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.store.set_meta("last_error", error)
            self.store.set_meta("last_error_at", now.isoformat())
            return {
                "snapshot": self.store.latest_account_snapshot(),
                "stale": True,
                "error": error,
            }


def inspect_runtime(
    *,
    state_path: Path,
    log_path: Path,
    now: datetime | None = None,
    process_running: bool | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    state = _read_json(state_path)
    latest_info = None
    latest_error = None
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = LOG_PATTERN.match(line)
            if not match:
                continue
            timestamp = datetime.strptime(
                match.group("timestamp"), "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=ZoneInfo("Asia/Seoul")).astimezone(timezone.utc)
            entry = (timestamp, match.group("message"))
            if match.group("level") == "INFO":
                latest_info = entry
            elif match.group("level") in {"ERROR", "CRITICAL"}:
                latest_error = entry
    if process_running is None:
        process_running = _live_process_running()
    heartbeat_age = (
        (now - latest_info[0]).total_seconds()
        if latest_info is not None
        else None
    )
    health = "normal"
    if not process_running or heartbeat_age is None or heartbeat_age > 60:
        health = "danger"
    elif heartbeat_age > 35:
        health = "warning"
    if latest_error and (latest_info is None or latest_error[0] > latest_info[0]):
        health = "danger"
    return {
        "health": health,
        "process_running": process_running,
        "last_watch_at": latest_info[0].isoformat() if latest_info else None,
        "last_error": latest_error[1] if latest_error else None,
        "phase": state.get("phase", "unknown"),
        "pending_order": state.get("pending_order"),
        "emergency_confirmations": state.get("emergency_confirmations", 0),
        "emergency_reason": state.get("emergency_reason"),
        "last_completed_candle": state.get("last_completed_candle"),
    }


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _live_process_running() -> bool:
    try:
        import psutil
    except ImportError:
        return False
    for process in psutil.process_iter(["cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if "run-auto-5m" in command and "--live" in command:
            return True
    return False
