import os

import requests


class NotificationError(RuntimeError):
    pass


class TelegramNotifier:
    def __init__(self, *, token: str | None = None, chat_id: str | None = None, session=None) -> None:
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")
        self.session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            response = self.session.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=10,
            )
            response.raise_for_status()
        except Exception:
            raise NotificationError("Telegram message delivery failed") from None
        return True


def startup_message(*, phase: str, hunt_balance: str, krw_balance: str, live: bool) -> str:
    return (
        f"[HUNT BOT START] mode={'live' if live else 'dry-run'} phase={phase} "
        f"HUNT={hunt_balance} KRW={krw_balance}"
    )


def shutdown_message(*, phase: str) -> str:
    return f"[HUNT BOT STOP] phase={phase}"


def order_submitted_message(*, action: str, identifier: str, order_uuid: str | None) -> str:
    return f"[ORDER SUBMITTED] action={action} identifier={identifier} uuid={order_uuid}"


def trade_completed_message(
    *,
    action: str,
    rsi_value: float | None,
    price: str,
    quantity: str,
    funds: str,
    order_uuid: str,
    next_phase: str,
) -> str:
    return (
        f"[TRADE COMPLETE] action={action} rsi={rsi_value} price={price} "
        f"quantity={quantity} funds={funds} uuid={order_uuid} next_phase={next_phase}"
    )


def emergency_detected_message(*, reason: str, high_drop_pct: str, average_loss_pct: str | None) -> str:
    return (
        f"[EMERGENCY DETECTED] reason={reason} high_drop={high_drop_pct}% "
        f"average_loss={average_loss_pct}%"
    )


def error_message(message: str) -> str:
    return f"[HUNT BOT ERROR] {message}"


def recovery_message(message: str) -> str:
    return f"[HUNT BOT RECOVERED] {message}"
