import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from huntbot.config import STATE_DIR


AUTO_STATE_PATH = STATE_DIR / "auto-trading.json"


@dataclass(frozen=True)
class PendingOrder:
    identifier: str
    action: str
    next_phase: str
    candle_timestamp: str | None
    rsi_value: float | None
    requested_amount: Decimal
    uuid: str | None = None


@dataclass(frozen=True)
class AutoTradeState:
    phase: str = "sell_1"
    last_completed_candle: str | None = None
    pending_order: PendingOrder | None = None
    emergency_confirmations: int = 0
    emergency_reason: str | None = None


def load_auto_state(path: Path = AUTO_STATE_PATH) -> AutoTradeState:
    if not path.exists():
        return AutoTradeState()
    data = json.loads(path.read_text(encoding="utf-8"))
    pending_data = data.get("pending_order")
    pending = None
    if pending_data:
        pending = PendingOrder(
            identifier=pending_data["identifier"],
            action=pending_data["action"],
            next_phase=pending_data["next_phase"],
            candle_timestamp=pending_data.get("candle_timestamp"),
            rsi_value=pending_data.get("rsi_value"),
            requested_amount=Decimal(str(pending_data["requested_amount"])),
            uuid=pending_data.get("uuid"),
        )
    return AutoTradeState(
        phase=data.get("phase", "sell_1"),
        last_completed_candle=data.get("last_completed_candle"),
        pending_order=pending,
        emergency_confirmations=int(data.get("emergency_confirmations", 0)),
        emergency_reason=data.get("emergency_reason"),
    )


def save_auto_state(state: AutoTradeState, path: Path = AUTO_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    if payload["pending_order"]:
        payload["pending_order"]["requested_amount"] = str(state.pending_order.requested_amount)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)
