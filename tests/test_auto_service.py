from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import huntbot.__main__ as huntbot_main
from huntbot.__main__ import build_parser
from huntbot.auto_service import (
    PosixFileLockBackend,
    SingleInstanceLock,
    initialize_auto_state,
    run_auto_service,
    unlock_emergency,
)
from huntbot.auto_state import AutoTradeState, load_auto_state, save_auto_state
from huntbot.trader import BuybackState, save_buyback_state
from huntbot.second_data import SecondCandle, save_second_snapshot


def test_run_auto_parser_requires_mode():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run-auto-5m"])
    assert parser.parse_args(["run-auto-5m", "--dry-run", "--once"]).once is True
    assert parser.parse_args(["run-auto-5m", "--live"]).live is True


def test_intrabar_backtest_parser_accepts_snapshot_and_days():
    args = build_parser().parse_args([
        "backtest-intrabar-rsi",
        "--snapshot", "data/backtests/test-seconds.csv",
        "--days", "90",
    ])

    assert args.snapshot.endswith("test-seconds.csv")
    assert args.days == 90


def test_intrabar_backtest_parser_defaults():
    args = build_parser().parse_args(["backtest-intrabar-rsi"])

    assert args.snapshot is None
    assert args.days == 90


def test_bitget_btc_rsi_optimizer_parser_accepts_cached_inputs():
    args = build_parser().parse_args([
        "optimize-bitget-btc-rsi",
        "--months",
        "6",
        "--candles",
        "candles.csv",
        "--funding",
        "funding.csv",
    ])

    assert args.command == "optimize-bitget-btc-rsi"
    assert args.months == 6
    assert args.candles == "candles.csv"
    assert args.funding == "funding.csv"


def test_bitget_btc_trend_walkforward_parser_accepts_cached_inputs():
    args = build_parser().parse_args([
        "walkforward-bitget-btc-trend",
        "--candles",
        "candles.csv",
        "--funding",
        "funding.csv",
        "--train-months",
        "6",
        "--test-months",
        "3",
    ])

    assert args.command == "walkforward-bitget-btc-trend"
    assert args.candles == "candles.csv"
    assert args.funding == "funding.csv"
    assert args.train_months == 6
    assert args.test_months == 3


def test_bitget_btc_paper_parser_accepts_once_and_lookback():
    args = build_parser().parse_args([
        "run-bitget-btc-paper",
        "--once",
        "--lookback",
        "40",
        "--initial-equity",
        "3000",
    ])

    assert args.command == "run-bitget-btc-paper"
    assert args.once is True
    assert args.lookback == 40
    assert args.initial_equity == "3000"


def test_bitget_btc_paper_command_uses_public_candles_without_live_orders(monkeypatch, tmp_path):
    class Result:
        action = "open_long"
        price = Decimal("100")
        equity = Decimal("1001")
        return_pct = Decimal("0.1")
        max_drawdown_pct = Decimal("0")
        signal_timestamp = datetime(2026, 7, 1, tzinfo=timezone.utc)
        target_position = "long"
        state = SimpleNamespace(position="long")

    captured = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(huntbot_main, "BitgetPublicClient", lambda: object())
    monkeypatch.setattr(huntbot_main, "download_recent_contract_candles", lambda client, count: ["candle"])
    monkeypatch.setattr(huntbot_main, "load_paper_state", lambda: "state")
    def run_cycle(candles, state, config):
        captured["config"] = config
        return Result()

    monkeypatch.setattr(huntbot_main, "run_paper_cycle", run_cycle)
    monkeypatch.setattr(huntbot_main, "append_paper_log", lambda result: captured.setdefault("logged", result))

    assert huntbot_main.run_bitget_btc_paper_command(once=True, lookback=40, initial_equity=Decimal("3000")) == 0
    assert captured["config"].lookback == 40
    assert captured["logged"].action == "open_long"


def test_intrabar_default_download_uses_public_client_window_and_snapshot(monkeypatch):
    now = datetime.now(timezone.utc)
    seconds = [
        SecondCandle("KRW-HUNT", now, *(Decimal("100"),) * 4, Decimal("1")),
        SecondCandle("KRW-HUNT", now + timedelta(seconds=1), *(Decimal("100"),) * 4, Decimal("1")),
    ]
    client = object()
    captured = {}
    monkeypatch.setattr(huntbot_main, "UpbitClient", lambda: client)
    monkeypatch.setattr(huntbot_main, "run_timing_study", lambda loaded: object())
    monkeypatch.setattr(huntbot_main, "write_timing_outputs", lambda *args: None)

    def download(received_client, market, *, start, end, snapshot_path):
        captured.update(client=received_client, market=market, start=start, end=end, snapshot_path=snapshot_path)
        return seconds

    monkeypatch.setattr(huntbot_main, "download_second_candles", download)

    assert huntbot_main.run_intrabar_rsi_command(snapshot=None, days=90) == 0
    assert captured["client"] is client
    assert captured["market"] == "KRW-HUNT"
    assert captured["end"] - captured["start"] == timedelta(days=90)
    assert captured["snapshot_path"] == Path("data/backtests/krw-hunt-1s-latest.csv")


def test_intrabar_snapshot_command_writes_json_and_markdown(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snapshot = tmp_path / "seconds.csv"
    seconds = [
        SecondCandle(
            "KRW-HUNT",
            datetime(2026, 6, 30, 0, 0, second, tzinfo=timezone.utc),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("1"),
        )
        for second in (0, 2)
    ]
    save_second_snapshot(seconds, snapshot)
    study = object()
    monkeypatch.setattr(huntbot_main, "run_timing_study", lambda loaded: study if loaded == seconds else None)
    monkeypatch.setattr(huntbot_main, "timing_study_to_json", lambda value, metadata: f"json:{metadata['missing_trade_seconds']}")
    monkeypatch.setattr(huntbot_main, "render_timing_study_markdown", lambda value, metadata: "markdown")

    assert huntbot_main.run_intrabar_rsi_command(snapshot=str(snapshot), days=90) == 0

    assert (tmp_path / "data/backtests/intrabar-rsi-study-latest.json").read_text() == "json:1"
    assert (tmp_path / "docs/intrabar-rsi-comparison-latest.md").read_text() == "markdown"


def test_initialize_auto_state_migrates_legacy_buyback_phase(tmp_path):
    auto_path = tmp_path / "auto.json"
    legacy_path = tmp_path / "buyback.json"
    save_buyback_state(BuybackState(phase="buy_2"), legacy_path)

    state = initialize_auto_state(auto_path=auto_path, legacy_path=legacy_path)

    assert state.phase == "buy_2"
    assert load_auto_state(auto_path).phase == "buy_2"


def test_unlock_emergency_requires_halt_and_no_pending_order(tmp_path):
    path = tmp_path / "auto.json"
    save_auto_state(
        AutoTradeState(
            phase="emergency_halt",
            rsi_signal_action="buy_1",
            rsi_signal_started_at="2026-07-02T00:00:00+00:00",
            rsi_signal_last_seen_at="2026-07-02T00:00:10+00:00",
            rsi_signal_candle="2026-07-02T00:00:00+00:00",
        ),
        path,
    )

    result = unlock_emergency(state_path=path, confirmation="UNLOCK KRW-HUNT")

    assert result.phase == "sell_1"
    saved = load_auto_state(path)
    assert saved.phase == "sell_1"
    assert saved.rsi_signal_action is None
    assert saved.rsi_signal_started_at is None


def test_unlock_emergency_rejects_wrong_confirmation(tmp_path):
    path = tmp_path / "auto.json"
    save_auto_state(AutoTradeState(phase="emergency_halt"), path)

    with pytest.raises(ValueError, match="confirmation"):
        unlock_emergency(state_path=path, confirmation="WRONG")


def test_dry_run_service_uses_separate_state_path(monkeypatch, tmp_path):
    captured = {}
    dry_path = tmp_path / "dry.json"
    monkeypatch.setattr("huntbot.auto_service.AUTO_DRY_RUN_STATE_PATH", dry_path)
    monkeypatch.setattr(
        "huntbot.auto_service.run_auto_cycle",
        lambda **kwargs: captured.setdefault("path", kwargs["state_path"]) or None,
    )

    class Client:
        def get_accounts(self):
            return []

    class Notifier:
        def send(self, message):
            return True

    with pytest.raises(AttributeError):
        run_auto_service(
            client=Client(),
            live=False,
            once=True,
            notifier=Notifier(),
            log_dir=tmp_path / "logs",
        )
    assert captured["path"] == dry_path


def test_one_shot_dry_run_does_not_send_shutdown_notification(monkeypatch, tmp_path):
    dry_path = tmp_path / "dry.json"
    monkeypatch.setattr("huntbot.auto_service.AUTO_DRY_RUN_STATE_PATH", dry_path)

    class Result:
        status = "waiting"
        phase = "sell_1"
        action = None
        current_price = 127
        rsi_value = 55
        risk_confirmed = False
        risk_reason = None
        high_drop_pct = 0
        average_loss_pct = 0
        order_uuid = None

    monkeypatch.setattr("huntbot.auto_service.run_auto_cycle", lambda **kwargs: Result())

    class Client:
        def get_accounts(self):
            return []

    class Notifier:
        def __init__(self):
            self.messages = []

        def send(self, message):
            self.messages.append(message)
            return True

    notifier = Notifier()

    assert run_auto_service(
        client=Client(),
        live=False,
        once=True,
        notifier=notifier,
        log_dir=tmp_path / "logs",
    ) == 0

    assert any("[HUNT BOT START]" in message for message in notifier.messages)
    assert not any("[HUNT BOT STOP]" in message for message in notifier.messages)


def test_live_startup_failure_does_not_send_shutdown_without_start(monkeypatch, tmp_path):
    class Client:
        def get_accounts(self):
            raise RuntimeError("auth")

    class Notifier:
        def __init__(self):
            self.messages = []

        def send(self, message):
            self.messages.append(message)
            return True

    notifier = Notifier()

    with pytest.raises(RuntimeError, match="auth"):
        run_auto_service(
            client=Client(),
            live=True,
            once=False,
            notifier=notifier,
            state_path=tmp_path / "auto.json",
            log_dir=tmp_path / "logs",
        )

    assert notifier.messages == []


def test_failed_cycle_resets_emergency_confirmation(monkeypatch, tmp_path):
    path = tmp_path / "auto.json"
    save_auto_state(AutoTradeState(phase="buy_2", emergency_confirmations=1), path)
    monkeypatch.setattr(
        "huntbot.auto_service.run_auto_cycle",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("network")),
    )

    class Client:
        def get_accounts(self):
            return []

    class Notifier:
        def send(self, message):
            return True

    with pytest.raises(RuntimeError, match="network"):
        run_auto_service(
            client=Client(),
            live=False,
            once=True,
            notifier=Notifier(),
            state_path=path,
            log_dir=tmp_path / "logs",
        )
    assert load_auto_state(path).emergency_confirmations == 0


def test_single_instance_lock_uses_injected_backend_and_releases(tmp_path):
    events = []

    class Backend:
        def acquire(self, handle):
            events.append(("acquire", handle.closed))

        def release(self, handle):
            events.append(("release", handle.closed))

    path = tmp_path / "auto.lock"

    with SingleInstanceLock(path=path, backend=Backend()):
        assert path.read_bytes() == b"0"

    assert events == [("acquire", False), ("release", False)]


def test_posix_backend_uses_exclusive_nonblocking_flock():
    calls = []

    class Fcntl:
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8

        @staticmethod
        def flock(file_descriptor, operation):
            calls.append((file_descriptor, operation))

    backend = PosixFileLockBackend(Fcntl)

    backend.acquire(type("Handle", (), {"fileno": lambda self: 17})())
    backend.release(type("Handle", (), {"fileno": lambda self: 17})())

    assert calls == [(17, Fcntl.LOCK_EX | Fcntl.LOCK_NB), (17, Fcntl.LOCK_UN)]
