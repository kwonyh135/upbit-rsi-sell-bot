import sqlite3
from decimal import Decimal
from pathlib import Path


ORDER_COLUMNS = (
    "uuid",
    "identifier",
    "action",
    "side",
    "state",
    "created_at",
    "completed_at",
    "executed_volume",
    "executed_funds",
    "average_price",
    "paid_fee",
    "next_phase",
    "is_emergency",
)


class DashboardStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS orders (
                    uuid TEXT PRIMARY KEY,
                    identifier TEXT,
                    action TEXT NOT NULL,
                    side TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT,
                    completed_at TEXT,
                    executed_volume TEXT NOT NULL,
                    executed_funds TEXT NOT NULL,
                    average_price TEXT NOT NULL,
                    paid_fee TEXT NOT NULL,
                    next_phase TEXT,
                    is_emergency INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    collected_at TEXT PRIMARY KEY,
                    hunt_balance TEXT NOT NULL,
                    krw_balance TEXT NOT NULL,
                    average_buy_price TEXT NOT NULL,
                    best_bid TEXT NOT NULL,
                    rsi REAL,
                    account_value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candles (
                    timestamp TEXT PRIMARY KEY,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    rsi REAL
                );
                CREATE TABLE IF NOT EXISTS sync_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    def upsert_order(self, order: dict) -> None:
        values = []
        for column in ORDER_COLUMNS:
            value = order.get(column)
            if isinstance(value, Decimal):
                value = str(value)
            if column == "is_emergency":
                value = int(bool(value))
            values.append(value)
        placeholders = ", ".join("?" for _ in ORDER_COLUMNS)
        updates = ", ".join(
            f"{column}=excluded.{column}" for column in ORDER_COLUMNS if column != "uuid"
        )
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO orders ({", ".join(ORDER_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT(uuid) DO UPDATE SET {updates}
                """,
                values,
            )

    def list_orders(self, *, newest_first: bool = False) -> list[dict]:
        direction = "DESC" if newest_first else "ASC"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM orders ORDER BY COALESCE(completed_at, created_at) {direction}"
            ).fetchall()
        return [self._decode_order(row) for row in rows]

    def has_order(self, uuid: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM orders WHERE uuid = ?", (uuid,)
            ).fetchone()
        return row is not None

    def save_account_snapshot(self, snapshot: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO account_snapshots (
                    collected_at, hunt_balance, krw_balance, average_buy_price,
                    best_bid, rsi, account_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collected_at) DO UPDATE SET
                    hunt_balance=excluded.hunt_balance,
                    krw_balance=excluded.krw_balance,
                    average_buy_price=excluded.average_buy_price,
                    best_bid=excluded.best_bid,
                    rsi=excluded.rsi,
                    account_value=excluded.account_value
                """,
                (
                    snapshot["collected_at"],
                    str(snapshot["hunt_balance"]),
                    str(snapshot["krw_balance"]),
                    str(snapshot["average_buy_price"]),
                    str(snapshot["best_bid"]),
                    snapshot.get("rsi"),
                    str(snapshot["account_value"]),
                ),
            )

    def latest_account_snapshot(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM account_snapshots ORDER BY collected_at DESC LIMIT 1"
            ).fetchone()
        return self._decode_snapshot(row) if row else None

    def list_account_snapshots(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM account_snapshots ORDER BY collected_at ASC"
            ).fetchall()
        return [self._decode_snapshot(row) for row in rows]

    def upsert_candle(self, candle: dict) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO candles (timestamp, open, high, low, close, rsi)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, rsi=excluded.rsi
                """,
                (
                    candle["timestamp"],
                    str(candle["open"]),
                    str(candle["high"]),
                    str(candle["low"]),
                    str(candle["close"]),
                    candle.get("rsi"),
                ),
            )

    def list_candles(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM candles ORDER BY timestamp ASC"
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "open": Decimal(row["open"]),
                "high": Decimal(row["high"]),
                "low": Decimal(row["low"]),
                "close": Decimal(row["close"]),
                "rsi": row["rsi"],
            }
            for row in rows
        ]

    def set_meta(self, key: str, value: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM sync_meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    @staticmethod
    def _decode_order(row) -> dict:
        data = dict(row)
        for key in ("executed_volume", "executed_funds", "average_price", "paid_fee"):
            data[key] = Decimal(data[key])
        data["is_emergency"] = bool(data["is_emergency"])
        return data

    @staticmethod
    def _decode_snapshot(row) -> dict:
        data = dict(row)
        for key in (
            "hunt_balance",
            "krw_balance",
            "average_buy_price",
            "best_bid",
            "account_value",
        ):
            data[key] = Decimal(data[key])
        return data
