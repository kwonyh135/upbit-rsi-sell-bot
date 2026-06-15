from pathlib import Path

import pytest

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


def test_run_auto_parser_requires_mode():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run-auto-5m"])
    assert parser.parse_args(["run-auto-5m", "--dry-run", "--once"]).once is True
    assert parser.parse_args(["run-auto-5m", "--live"]).live is True


def test_initialize_auto_state_migrates_legacy_buyback_phase(tmp_path):
    auto_path = tmp_path / "auto.json"
    legacy_path = tmp_path / "buyback.json"
    save_buyback_state(BuybackState(phase="buy_2"), legacy_path)

    state = initialize_auto_state(auto_path=auto_path, legacy_path=legacy_path)

    assert state.phase == "buy_2"
    assert load_auto_state(auto_path).phase == "buy_2"


def test_unlock_emergency_requires_halt_and_no_pending_order(tmp_path):
    path = tmp_path / "auto.json"
    save_auto_state(AutoTradeState(phase="emergency_halt"), path)

    result = unlock_emergency(state_path=path, confirmation="UNLOCK KRW-HUNT")

    assert result.phase == "sell_1"
    assert load_auto_state(path).phase == "sell_1"


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
