from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


MARKET = "KRW-HUNT"
RSI_PERIOD = 14
INITIAL_BACKTEST_KRW = 3_000_000
MIN_HOLDING_VALUE_KRW = 500_000
DEFAULT_SERVER_URL = "https://api.upbit.com"
DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"
STATE_DIR = DATA_DIR / "state"
LOG_DIR = Path("logs")
AUTO_STATE_PATH = STATE_DIR / "auto-trading.json"
AUTO_DRY_RUN_STATE_PATH = STATE_DIR / "auto-trading-dry-run.json"
AUTO_LOCK_PATH = STATE_DIR / "auto-trading.lock"
EMERGENCY_HIGH_DROP_PCT = Decimal("7")
EMERGENCY_AVG_LOSS_PCT = Decimal("10")
EMERGENCY_CONFIRMATIONS = 2
AUTO_POLL_SECONDS = 10


def load_environment() -> None:
    load_dotenv()
