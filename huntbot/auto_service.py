import logging
import os
import time
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path

from huntbot.auto_state import AUTO_STATE_PATH, AutoTradeState, load_auto_state, save_auto_state
from huntbot.auto_trader import run_auto_cycle
from huntbot.config import AUTO_DRY_RUN_STATE_PATH, AUTO_LOCK_PATH, AUTO_POLL_SECONDS, LOG_DIR
from huntbot.notifier import (
    NotificationError,
    TelegramNotifier,
    error_message,
    recovery_message,
    shutdown_message,
    startup_message,
)
from huntbot.trader import BUYBACK_STATE_PATH, load_buyback_state


LOGGER = logging.getLogger("huntbot.auto")


class WindowsFileLockBackend:
    def __init__(self, module=None) -> None:
        if module is None:
            import msvcrt

            module = msvcrt
        self.module = module

    def acquire(self, handle) -> None:
        handle.seek(0)
        self.module.locking(handle.fileno(), self.module.LK_NBLCK, 1)

    def release(self, handle) -> None:
        handle.seek(0)
        self.module.locking(handle.fileno(), self.module.LK_UNLCK, 1)


class PosixFileLockBackend:
    def __init__(self, module=None) -> None:
        if module is None:
            import fcntl

            module = fcntl
        self.module = module

    def acquire(self, handle) -> None:
        self.module.flock(
            handle.fileno(),
            self.module.LOCK_EX | self.module.LOCK_NB,
        )

    def release(self, handle) -> None:
        self.module.flock(handle.fileno(), self.module.LOCK_UN)


def default_file_lock_backend():
    if os.name == "nt":
        return WindowsFileLockBackend()
    return PosixFileLockBackend()


def initialize_auto_state(
    *,
    auto_path: Path = AUTO_STATE_PATH,
    legacy_path: Path = BUYBACK_STATE_PATH,
) -> AutoTradeState:
    if auto_path.exists():
        return load_auto_state(auto_path)
    legacy = load_buyback_state(legacy_path)
    state = AutoTradeState(phase=legacy.phase)
    save_auto_state(state, auto_path)
    return state


def unlock_emergency(
    *,
    state_path: Path = AUTO_STATE_PATH,
    confirmation: str,
) -> AutoTradeState:
    state = load_auto_state(state_path)
    if confirmation != "UNLOCK KRW-HUNT":
        raise ValueError("invalid emergency unlock confirmation")
    if state.phase != "emergency_halt":
        raise ValueError("bot is not in emergency_halt")
    if state.pending_order is not None:
        raise ValueError("pending order must be reconciled before unlock")
    next_state = replace(state, phase="sell_1", emergency_confirmations=0, emergency_reason=None)
    save_auto_state(next_state, state_path)
    return next_state


def configure_logging(log_dir: Path = LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    if LOGGER.handlers:
        return
    handler = RotatingFileHandler(
        log_dir / "huntbot-auto.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


class SingleInstanceLock:
    def __init__(self, path: Path = AUTO_LOCK_PATH, backend=None) -> None:
        self.path = path
        self.backend = backend or default_file_lock_backend()
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
        try:
            self.backend.acquire(self.handle)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("another auto-trading process is already running") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is None:
            return
        try:
            self.backend.release(self.handle)
        finally:
            self.handle.close()
            self.handle = None


def run_auto_service(
    *,
    client,
    live: bool,
    once: bool = False,
    notifier=None,
    sleep=time.sleep,
    state_path: Path | None = None,
    log_dir: Path = LOG_DIR,
) -> int:
    configure_logging(log_dir)
    notifier = notifier or TelegramNotifier()
    state_path = state_path or (AUTO_STATE_PATH if live else AUTO_DRY_RUN_STATE_PATH)
    state = initialize_auto_state(auto_path=state_path)
    last_error = None
    service_started = False
    try:
        accounts = client.get_accounts()
        hunt = next((item.get("balance", "0") for item in accounts if item.get("currency") == "HUNT"), "0")
        krw = next((item.get("balance", "0") for item in accounts if item.get("currency") == "KRW"), "0")
        _notify(notifier, startup_message(phase=state.phase, hunt_balance=hunt, krw_balance=krw, live=live))
        service_started = True
        while True:
            try:
                result = run_auto_cycle(
                    client=client,
                    notifier=notifier,
                    state_path=state_path,
                    live=live,
                )
                LOGGER.info(
                    "status=%s phase=%s action=%s price=%s rsi=%s risk=%s reason=%s uuid=%s",
                    result.status,
                    result.phase,
                    result.action,
                    result.current_price,
                    result.rsi_value,
                    result.risk_confirmed,
                    result.risk_reason,
                    result.order_uuid,
                )
                print(
                    f"mode={'live' if live else 'dry-run'} status={result.status} phase={result.phase} "
                    f"action={result.action} price={result.current_price} rsi={result.rsi_value} "
                    f"risk_confirmed={result.risk_confirmed} risk_reason={result.risk_reason} "
                    f"high_drop_pct={result.high_drop_pct} average_loss_pct={result.average_loss_pct} "
                    f"order_uuid={result.order_uuid}"
                )
                if last_error is not None:
                    _notify(notifier, recovery_message(last_error))
                    last_error = None
                if once:
                    return 0
                sleep(AUTO_POLL_SECONDS)
            except KeyboardInterrupt:
                return 0
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                LOGGER.exception("auto trading cycle failed")
                _reset_emergency_confirmation(state_path)
                if message != last_error:
                    _notify(notifier, error_message(message))
                    last_error = message
                if once:
                    raise
                sleep(min(AUTO_POLL_SECONDS * 3, 60))
    finally:
        if live and service_started:
            final_state = load_auto_state(state_path)
            _notify(notifier, shutdown_message(phase=final_state.phase))


def _notify(notifier, message: str) -> None:
    try:
        notifier.send(message)
    except NotificationError:
        LOGGER.exception("Telegram notification failed")


def _reset_emergency_confirmation(state_path: Path) -> None:
    try:
        state = load_auto_state(state_path)
        if state.emergency_confirmations or state.emergency_reason:
            save_auto_state(
                replace(state, emergency_confirmations=0, emergency_reason=None),
                state_path,
            )
    except Exception:
        LOGGER.exception("Failed to reset emergency confirmation state")
