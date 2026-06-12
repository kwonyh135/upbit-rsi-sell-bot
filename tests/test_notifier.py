import pytest

from huntbot.notifier import NotificationError, TelegramNotifier, trade_completed_message


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "telegram error"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.text)


class FakeSession:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        return FakeResponse(self.status_code)


def test_disabled_notifier_does_not_send():
    session = FakeSession()
    notifier = TelegramNotifier(token="", chat_id="", session=session)

    assert notifier.send("test") is False
    assert session.calls == []


def test_notifier_posts_plain_text_message():
    session = FakeSession()
    notifier = TelegramNotifier(token="secret-token", chat_id="1234", session=session)

    assert notifier.send("bot started") is True
    url, body, timeout = session.calls[0]
    assert url.endswith("/botsecret-token/sendMessage")
    assert body == {"chat_id": "1234", "text": "bot started"}
    assert timeout == 10


def test_notifier_wraps_transport_failure_without_exposing_token():
    notifier = TelegramNotifier(token="secret-token", chat_id="1234", session=FakeSession(500))

    with pytest.raises(NotificationError) as error:
        notifier.send("failure")

    assert "secret-token" not in str(error.value)
    assert error.value.__cause__ is None


def test_trade_completed_message_contains_reconciliation_details():
    message = trade_completed_message(
        action="emergency_sell",
        rsi_value=30.5,
        price="90",
        quantity="1000",
        funds="90000",
        order_uuid="order-1",
        next_phase="emergency_halt",
    )
    assert "emergency_sell" in message
    assert "order-1" in message
    assert "emergency_halt" in message
